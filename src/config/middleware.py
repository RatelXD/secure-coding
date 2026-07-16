"""Cross-entrypoint policy middleware."""

from collections.abc import Callable

from django.http import HttpRequest, HttpResponse


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
