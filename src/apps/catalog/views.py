from __future__ import annotations



from django.contrib.auth.decorators import login_required
from django.db import connection, transaction
from django.db.models import Prefetch
from django.views.decorators.http import require_POST

from django.http import Http404, HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from apps.accounts.services import project_account_identity
from apps.moderation.services import visible_products

from .projectors import ProductState, effective_product_state
from .forms import ProductCreateForm, ProductUpdateForm
from .models import Category, Favorite, Product, ProductImage, Region
from .engagement import record_product_view, set_favorite
from .search import InvalidProductSearch, parse_product_search, search_products
from .services import (
    _persist_exception_cleanup_failures,
    _record_cleanup_failures,
    is_product_public,
    replace_product_images,
)


def product_list(request: HttpRequest) -> HttpResponse:
    try:
        search = parse_product_search(request.GET)
    except InvalidProductSearch as exc:
        return HttpResponse(str(exc), status=400)

    products, total_count = search_products(search)
    db_now = _database_now()
    for product in products:
        _attach_effective_state(product=product, db_now=db_now)
    return render(
        request,
        "catalog/product_list.html",
        {
            "products": products,
            "regions": Region.objects.all(),
            "categories": Category.objects.all(),
            "search": search,
            "total_count": total_count,
            "has_previous": search.page > 1,
            "has_next": search.page * 20 < total_count,
            "previous_page": search.page - 1,
            "next_page": search.page + 1,
            "selected_region_code": search.region,
            "region_error": False,
        },
    )


def product_detail(request: HttpRequest, pk: int) -> HttpResponse:
    product = get_object_or_404(
        Product.objects.filter(archived_at__isnull=True)
        .select_related("owner", "category", "region")
        .prefetch_related(
            Prefetch(
                "images",
                queryset=ProductImage.objects.filter(promotion_state="PROMOTED"),
            )
        ),
        pk=pk,
    )
    if not is_product_public(product_id=product.pk):
        raise Http404
    _attach_effective_state(product=product, db_now=_database_now())
    metric = record_product_view(request=request, product=product)
    is_favorite = (
        request.user.is_authenticated
        and Favorite.objects.filter(user=request.user, product=product).exists()
    )
    return render(
        request,
        "catalog/product_detail.html",
        {
            "product": product,
            "seller_identity": project_account_identity(user=product.owner),
            "metric": metric,
            "is_favorite": is_favorite,
        },
    )


@login_required
def product_create(request: HttpRequest) -> HttpResponse:
    form = ProductCreateForm(request.POST or None, request.FILES or None)
    if request.method == "POST" and form.is_valid():
        staging = None
        try:
            with transaction.atomic():
                product = form.save(commit=False)
                product.owner = request.user
                product.region_source = (
                    Product.RegionSource.SELECTED
                    if product.region_id is not None
                    else Product.RegionSource.LEGACY_UNSET
                )
                product.save()
                staging = replace_product_images(
                    product=product,
                    images=form.cleaned_data["images"],
                )
        except Exception as exc:
            if staging is not None:
                _record_cleanup_failures(exc=exc, keys=staging.cleanup())
            _persist_exception_cleanup_failures(exc=exc)
            raise
        return redirect("catalog:detail", pk=product.pk)
    return render(request, "catalog/product_form.html", {"form": form, "mode": "create"})


@login_required
def product_update(request: HttpRequest, pk: int) -> HttpResponse:
    product = get_object_or_404(
        Product,
        pk=pk,
        owner_id=request.user.pk,
        archived_at__isnull=True,
    )
    form = ProductUpdateForm(
        request.POST or None,
        request.FILES or None,
        instance=product,
        initial={"version": product.version},
    )
    if request.method != "POST" or not form.is_valid():
        return render(
            request,
            "catalog/product_form.html",
            {"form": form, "mode": "update", "product": product},
        )

    staging = None
    try:
        with transaction.atomic():
            locked = get_object_or_404(
                Product.objects.select_for_update(),
                pk=pk,
                owner_id=request.user.pk,
                archived_at__isnull=True,
            )
            if form.cleaned_data["version"] != locked.version:
                form.add_error(None, "다른 요청에서 상품이 변경되었습니다. 새로고침 후 다시 시도해 주세요.")
                return render(
                    request,
                    "catalog/product_form.html",
                    {"form": form, "mode": "update", "product": locked},
                    status=409,
                )

            locked.title = form.cleaned_data["title"]
            locked.description = form.cleaned_data["description"]
            locked.price = form.cleaned_data["price"]
            locked.category = form.cleaned_data["category"]
            locked.region = form.cleaned_data["region"]
            locked.region_source = (
                Product.RegionSource.SELECTED
                if locked.region_id is not None
                else Product.RegionSource.LEGACY_UNSET
            )
            locked.version += 1
            locked.save(
                update_fields=(
                    "title",
                    "description",
                    "price",
                    "category",
                    "region",
                    "region_source",
                    "version",
                    "updated_at",
                )
            )
            if form.cleaned_data["images"] or form.cleaned_data["clear_images"]:
                staging = replace_product_images(
                    product=locked,
                    images=form.cleaned_data["images"],
                )
    except Exception as exc:
        if staging is not None:
            _record_cleanup_failures(exc=exc, keys=staging.cleanup())
        _persist_exception_cleanup_failures(exc=exc)
        raise

    return redirect("catalog:detail", pk=locked.pk)


@login_required
def product_delete(request: HttpRequest, pk: int) -> HttpResponse:
    product = get_object_or_404(
        Product,
        pk=pk,
        owner_id=request.user.pk,
        archived_at__isnull=True,
    )
    if request.method != "POST":
        return render(request, "catalog/product_confirm_delete.html", {"product": product})

    try:
        submitted_version = int(request.POST.get("version", ""))
    except ValueError:
        submitted_version = -1

    with transaction.atomic():
        locked = get_object_or_404(
            Product.objects.select_for_update(),
            pk=pk,
            owner_id=request.user.pk,
            archived_at__isnull=True,
        )
        if submitted_version != locked.version:
            return HttpResponse("상품이 변경되었습니다. 새로고침 후 다시 시도해 주세요.", status=409)
        locked.archived_at = _database_now()
        locked.version += 1
        locked.save(update_fields=("archived_at", "version", "updated_at"))
    return redirect("catalog:list")


@login_required
@require_POST
def product_favorite(request: HttpRequest, pk: int) -> HttpResponse:
    product = get_object_or_404(Product, pk=pk, archived_at__isnull=True)
    if not is_product_public(product_id=product.pk):
        raise Http404
    action = request.POST.get("action")
    if set(request.POST) != {"action"} or action not in {"add", "remove"}:
        return HttpResponse("관심 명령이 올바르지 않습니다.", status=400)
    set_favorite(user_id=request.user.pk, product_id=product.pk, active=action == "add")
    return redirect("catalog:detail", pk=product.pk)


@login_required
def favorite_list(request: HttpRequest) -> HttpResponse:
    queryset = (
        Product.objects.filter(
            favorites__user=request.user,
            archived_at__isnull=True,
        )
        .select_related("owner", "category", "region")
        .prefetch_related(
            Prefetch(
                "images",
                queryset=ProductImage.objects.filter(promotion_state="PROMOTED"),
            )
        )
    )
    products = list(visible_products(queryset).order_by("-favorites__created_at", "-pk"))
    db_now = _database_now()
    for product in products:
        _attach_effective_state(product=product, db_now=db_now)
    return render(
        request,
        "catalog/favorite_list.html",
        {"products": products},
    )


_PRODUCT_STATE_LABELS = {
    ProductState.AVAILABLE: "판매 중",
    ProductState.RESERVED: "예약 중",
    ProductState.SOLD: "판매 완료",
}


def _attach_effective_state(*, product: Product, db_now) -> None:
    if hasattr(product, "lifecycle_status"):
        state = {
            "RESERVED": ProductState.RESERVED,
            "COMPLETED": ProductState.SOLD,
        }.get(product.lifecycle_status, ProductState.AVAILABLE)
    else:
        state = effective_product_state(product=product, db_now=db_now)
    product.effective_state = state.value
    product.effective_state_label = _PRODUCT_STATE_LABELS[state]


def _database_now():
    with connection.cursor() as cursor:
        cursor.execute("SELECT CURRENT_TIMESTAMP")
        value = cursor.fetchone()[0]
    if isinstance(value, str):
        value = parse_datetime(value)
    if value is None:
        raise RuntimeError("데이터베이스 현재 시각을 읽을 수 없습니다.")
    if timezone.is_naive(value):
        value = timezone.make_aware(value, timezone.get_current_timezone())
    return value
