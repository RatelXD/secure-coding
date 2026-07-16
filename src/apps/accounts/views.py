from django.contrib import messages
from django.contrib.auth import login, update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.http import Http404, HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_http_methods, require_POST

from .forms import BioForm, LoginForm, OwnPasswordChangeForm, SignupForm
from .models import User
from .services import SESSION_AUTH_EPOCH_KEY, authenticate_login
from .validators import canonicalize_username

_GENERIC_LOGIN_ERROR = "아이디 또는 비밀번호를 확인해 주세요. 잠시 후 다시 시도할 수 있습니다."


def home(request: HttpRequest) -> HttpResponse:
    return render(request, "home.html")


@require_http_methods(["GET", "POST"])
def signup(request: HttpRequest) -> HttpResponse:
    if request.user.is_authenticated:
        return redirect("accounts:profile")

    form = SignupForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        user = form.save()
        login(request, user)
        request.session[SESSION_AUTH_EPOCH_KEY] = user.auth_epoch
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
                request.session[SESSION_AUTH_EPOCH_KEY] = user.auth_epoch
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
    from django.contrib.auth import logout

    logout(request)
    return redirect("home")


def user_list(request: HttpRequest) -> HttpResponse:
    users = User.objects.only("id", "username", "bio").order_by("username")
    return render(request, "accounts/user_list.html", {"users": users})


def user_detail(request: HttpRequest, username: str) -> HttpResponse:
    try:
        canonical_username = canonicalize_username(username)
    except ValidationError as exc:
        raise Http404 from exc
    profile_user = get_object_or_404(
        User.objects.only("id", "username", "bio"),
        username=canonical_username,
    )
    return render(request, "accounts/user_detail.html", {"profile_user": profile_user})


@login_required
@require_http_methods(["GET"])
def profile(request: HttpRequest) -> HttpResponse:
    return render(request, "accounts/profile.html")


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
        update_session_auth_hash(request, user)
        messages.success(request, "비밀번호를 변경했습니다.")
        return redirect("accounts:profile")
    return render(request, "accounts/password_change.html", {"form": form})
