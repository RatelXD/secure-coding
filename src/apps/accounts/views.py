from enum import StrEnum
from typing import assert_never

from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.core.paginator import Page, Paginator
from django.db.models import OuterRef, Prefetch, Q, Subquery
from django.http import Http404, HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_http_methods, require_POST

from apps.catalog.models import Category, Favorite, Product, ProductImage
from apps.moderation.services import visible_products
from apps.trades.models import Trade
from apps.trades.services import public_reviews

from .forms import BioForm, LoginForm, OwnPasswordChangeForm, SignupForm, WithdrawalForm
from .models import User
from .services import AccountSessionService, authenticate_login, project_account_identity
from .validators import canonicalize_username
from .withdrawal import WithdrawalBlocked, WithdrawalUnavailable, withdraw_account

_GENERIC_LOGIN_ERROR = "아이디 또는 비밀번호를 확인해 주세요. 잠시 후 다시 시도할 수 있습니다."
_PROFILE_PAGE_SIZE = 8


class _ProfileProductFilter(StrEnum):
    ALL = "all"
    AVAILABLE = "available"
    SOLD = "sold"


def _profile_product_page(
    *,
    request: HttpRequest,
    owner_id: int,
) -> tuple[Page[Product], _ProfileProductFilter]:
    try:
        selected_filter = _ProfileProductFilter(request.GET.get("status", "all"))
    except ValueError:
        selected_filter = _ProfileProductFilter.ALL

    lifecycle_status = (
        Trade.objects.filter(
            product_id=OuterRef("pk"),
            status__in=(Trade.Status.RESERVED, Trade.Status.COMPLETED),
        )
        .values("status")[:1]
    )
    promoted_images = ProductImage.objects.filter(promotion_state="PROMOTED").order_by(
        "position", "pk"
    )
    products = visible_products(
        Product.objects.filter(owner_id=owner_id)
        .select_related("category", "region")
        .prefetch_related(
            Prefetch("images", queryset=promoted_images, to_attr="profile_images")
        )
    ).annotate(lifecycle_status=Subquery(lifecycle_status))
    match selected_filter:
        case _ProfileProductFilter.ALL:
            pass
        case _ProfileProductFilter.AVAILABLE:
            products = products.filter(
                Q(lifecycle_status__isnull=True)
                | ~Q(lifecycle_status=Trade.Status.COMPLETED)
            )
        case _ProfileProductFilter.SOLD:
            products = products.filter(lifecycle_status=Trade.Status.COMPLETED)
        case unreachable:
            assert_never(unreachable)
    paginator = Paginator(products.order_by("-created_at", "-pk"), _PROFILE_PAGE_SIZE)
    page = paginator.get_page(request.GET.get("page", "1"))
    return page, selected_filter


def _completed_trade_count(*, user_id: int) -> int:
    return (
        Trade.objects.filter(status=Trade.Status.COMPLETED)
        .filter(Q(seller_id=user_id) | Q(buyer_id=user_id))
        .distinct()
        .count()
    )


def home(request: HttpRequest) -> HttpResponse:
    latest_products = visible_products(
        Product.objects.select_related("category", "region").prefetch_related(
            Prefetch(
                "images",
                queryset=ProductImage.objects.filter(promotion_state="PROMOTED"),
            )
        )
    ).order_by("-created_at", "-pk")[:4]
    return render(
        request,
        "home.html",
        {
            "categories": Category.objects.order_by("display_order", "code"),
            "latest_products": latest_products,
        },
    )


@require_http_methods(["GET", "POST"])
def signup(request: HttpRequest) -> HttpResponse:
    if request.user.is_authenticated:
        return redirect("accounts:profile")

    form = SignupForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        user = form.save()
        login(request, user)
        AccountSessionService.start(request=request, user=user)
        messages.success(request, "회원가입이 완료되었습니다.")
        return redirect("accounts:profile")
    return render(request, "accounts/signup.html", {"form": form})


@require_http_methods(["GET", "POST"])
def login_view(request: HttpRequest) -> HttpResponse:
    if request.user.is_authenticated:
        return redirect("accounts:profile")

    form = LoginForm(request.POST or None)
    login_error = None
    if request.method == "POST":
        if form.is_valid():
            user = authenticate_login(
                request=request,
                username=form.cleaned_data["username"],
                password=form.cleaned_data["password"],
            )
            if user is not None:
                login(request, user)
                AccountSessionService.start(request=request, user=user)
                destination = request.POST.get("next", "")
                if not url_has_allowed_host_and_scheme(
                    destination,
                    allowed_hosts={request.get_host()},
                    require_https=request.is_secure(),
                ):
                    destination = reverse("home")
                return redirect(destination)
        login_error = _GENERIC_LOGIN_ERROR
    return render(
        request,
        "accounts/login.html",
        {"form": form, "login_error": login_error, "next": request.GET.get("next", "")},
    )


@require_POST
def logout_view(request: HttpRequest) -> HttpResponse:
    AccountSessionService.end(request=request)
    return redirect("home")


def user_list(request: HttpRequest) -> HttpResponse:
    users = []
    for user in User.objects.only("id", "username", "bio", "withdrawn_at").order_by("username"):
        identity = project_account_identity(user=user)
        users.append(
            {
                "canonical_username": user.username,
                "identity": identity,
                "bio": None if identity.is_tombstone else user.bio,
            }
        )
    return render(request, "accounts/user_list.html", {"users": users})


def user_detail(request: HttpRequest, username: str) -> HttpResponse:
    try:
        canonical_username = canonicalize_username(username)
    except ValidationError as exc:
        raise Http404 from exc
    profile_user = get_object_or_404(
        User.objects.only("id", "username", "bio", "withdrawn_at"),
        username=canonical_username,
    )
    identity = project_account_identity(user=profile_user)
    product_page = None
    selected_filter = _ProfileProductFilter.ALL
    activity_trade_count = None
    activity_review_count = None
    if not identity.is_tombstone:
        product_page, selected_filter = _profile_product_page(
            request=request,
            owner_id=profile_user.pk,
        )
        activity_trade_count = _completed_trade_count(user_id=profile_user.pk)
        activity_review_count = public_reviews().filter(subject_id=profile_user.pk).count()
    return render(
        request,
        "accounts/user_detail.html",
        {
            "profile_user": profile_user,
            "profile_identity": identity,
            "profile_bio": None if identity.is_tombstone else profile_user.bio,
            "product_page": product_page,
            "profile_filter": selected_filter.value,
            "activity_trade_count": activity_trade_count,
            "activity_review_count": activity_review_count,
            "show_report": (
                request.user.is_authenticated
                and request.user.pk != profile_user.pk
                and not identity.is_tombstone
            ),
        },
    )


@login_required
@require_http_methods(["GET"])
def profile(request: HttpRequest) -> HttpResponse:
    product_page, selected_filter = _profile_product_page(
        request=request,
        owner_id=request.user.pk,
    )
    return render(
        request,
        "accounts/profile.html",
        {
            "product_page": product_page,
            "profile_filter": selected_filter.value,
            "transaction_count": _completed_trade_count(user_id=request.user.pk),
            "favorite_count": Favorite.objects.filter(user_id=request.user.pk).count(),
        },
    )


@login_required
@require_http_methods(["GET", "POST"])
def bio_edit(request: HttpRequest) -> HttpResponse:
    form = BioForm(request.POST or None, instance=request.user)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "소개글을 변경했습니다.")
        return redirect("accounts:profile")
    return render(request, "accounts/bio_edit.html", {"form": form})


@login_required
@require_http_methods(["GET", "POST"])
def password_change(request: HttpRequest) -> HttpResponse:
    form = OwnPasswordChangeForm(user=request.user, data=request.POST or None)
    if request.method == "POST" and form.is_valid():
        user = form.save()
        AccountSessionService.rotate_after_password_change(request=request, user=user)
        messages.success(request, "비밀번호를 변경했습니다.")
        return redirect("accounts:profile")
    return render(request, "accounts/password_change.html", {"form": form})


@login_required
@require_http_methods(["GET", "POST"])
def withdraw(request: HttpRequest) -> HttpResponse:
    form = WithdrawalForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        try:
            withdraw_account(
                user_id=request.user.pk,
                password=form.cleaned_data["password"],
            )
        except WithdrawalBlocked as exc:
            form.add_error(None, str(exc))
        except WithdrawalUnavailable:
            return HttpResponse(
                "회원 탈퇴 권위를 확인할 수 없습니다. 잠시 후 다시 시도해 주세요.",
                status=503,
                content_type="text/plain",
            )
        else:
            AccountSessionService.end(request=request)
            messages.success(request, "회원 탈퇴가 완료되었습니다.")
            return redirect("home")
    return render(request, "accounts/withdraw.html", {"form": form})
