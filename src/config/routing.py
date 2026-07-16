"""Same-origin ASGI protocol routing."""

from channels.auth import AuthMiddlewareStack
from channels.routing import ProtocolTypeRouter, URLRouter
from channels.security.websocket import AllowedHostsOriginValidator
from django.core.handlers.asgi import ASGIHandler

from apps.chat.routing import websocket_urlpatterns


def build_protocol_router(http_application: ASGIHandler) -> ProtocolTypeRouter:
    return ProtocolTypeRouter(
        {
            "http": http_application,
            "websocket": AllowedHostsOriginValidator(
                AuthMiddlewareStack(URLRouter(websocket_urlpatterns))
            ),
        }
    )
