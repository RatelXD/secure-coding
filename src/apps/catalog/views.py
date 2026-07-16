from __future__ import annotations

from collections.abc import Callable

from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.db.models.deletion import ProtectedError
from django.http import Http404, HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render

from .forms import ProductCreateForm, ProductUpdateForm
from .models import Product
from .services import is_product_public


def product_list(request: HttpRequest) -> HttpResponse:
    candidates = Product.objects.select_related("owner").all()
    products = [product for product in candidates if is_product_public(product_id=product.pk)]
    return render(request, "catalog/product_list.html", {"products": products})


def product_detail(request: HttpRequest, pk: int) -> HttpResponse:
    product = get_object_or_404(Product.objects.select_related("owner"), pk=pk)
    if not is_product_public(product_id=product.pk):
        raise Http404
    return render(request, "catalog/product_detail.html", {"product": product})


@login_required
def product_create(request: HttpRequest) -> HttpResponse:
    form = ProductCreateForm(request.POST or None, request.FILES or None)
    if request.method == "POST" and form.is_valid():
        product = form.save(commit=False)
        product.owner = request.user
        product.save()
        return redirect("catalog:detail", pk=product.pk)
    return render(request, "catalog/product_form.html", {"form": form, "mode": "create"})


@login_required
def product_update(request: HttpRequest, pk: int) -> HttpResponse:
    product = get_object_or_404(Product, pk=pk, owner_id=request.user.pk)
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

    with transaction.atomic():
        locked = get_object_or_404(
            Product.objects.select_for_update(),
            pk=pk,
            owner_id=request.user.pk,
        )
        if form.cleaned_data["version"] != locked.version:
            form.add_error(None, "다른 요청에서 상품이 변경되었습니다. 새로고침 후 다시 시도해 주세요.")
            return render(
                request,
                "catalog/product_form.html",
                {"form": form, "mode": "update", "product": locked},
                status=409,
            )

        old_image_name = locked.image.name
        locked.title = form.cleaned_data["title"]
        locked.description = form.cleaned_data["description"]
        locked.price = form.cleaned_data["price"]
        locked.sale_state = form.cleaned_data["sale_state"]
        if form.cleaned_data["image"] is not None:
            locked.image = form.cleaned_data["image"]
        locked.version += 1
        locked.save(
            update_fields=(
                "title",
                "description",
                "price",
                "sale_state",
                "image",
                "version",
                "updated_at",
            )
        )
        if old_image_name and old_image_name != locked.image.name:
            _delete_after_commit(locked.image.storage.delete, old_image_name)

    return redirect("catalog:detail", pk=locked.pk)


@login_required
def product_delete(request: HttpRequest, pk: int) -> HttpResponse:
    product = get_object_or_404(Product, pk=pk, owner_id=request.user.pk)
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
        )
        if submitted_version != locked.version:
            return HttpResponse("상품이 변경되었습니다. 새로고침 후 다시 시도해 주세요.", status=409)
        image_name = locked.image.name
        storage_delete = locked.image.storage.delete
        try:
            locked.delete()
        except ProtectedError:
            return HttpResponse("신고 기록이 있는 상품은 삭제할 수 없습니다.", status=409)
        if image_name:
            _delete_after_commit(storage_delete, image_name)
    return redirect("catalog:list")


def _delete_after_commit(delete: Callable[[str], None], name: str) -> None:
    transaction.on_commit(lambda: delete(name))
