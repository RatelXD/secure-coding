"""Cross-entrypoint policy middleware."""

from collections.abc import Callable
from ipaddress import ip_address

from django.conf import settings
from django.http import HttpRequest, HttpResponse, HttpResponseBadRequest

_UNTRUSTED_FORWARDED_HEADERS = (
    "HTTP_FORWARDED",
    "HTTP_X_FORWARDED_FOR",
    "HTTP_X_FORWARDED_HOST",
    "HTTP_X_FORWARDED_PORT",
    "HTTP_X_REAL_IP",
)


class TrustedProxyHeadersMiddleware:
    """Trust only a single HTTPS assertion from an explicitly allowed proxy."""

    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        if not settings.TRUST_PROXY_HEADERS:
            return self.get_response(request)

        forwarded_proto = request.META.get("HTTP_X_FORWARDED_PROTO")
        if forwarded_proto is not None:
            try:
                remote_addr = str(ip_address(request.META.get("REMOTE_ADDR", "")))
            except ValueError:
                return HttpResponseBadRequest("Invalid proxy headers.")

            if (
                remote_addr not in settings.TRUSTED_PROXY_IPS
                or forwarded_proto != "https"
            ):
                return HttpResponseBadRequest("Invalid proxy headers.")

        for header in _UNTRUSTED_FORWARDED_HEADERS:
            request.META.pop(header, None)

        return self.get_response(request)


class CanonicalUserStatusMiddleware:
    """Apply the accounts DB-time status authority to authenticated HTTP requests."""

    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        if request.user.is_authenticated:
            from apps.accounts.services import enforce_http_user_status

            denial = enforce_http_user_status(request)
            if denial is not None:
                return denial
        return self.get_response(request)
