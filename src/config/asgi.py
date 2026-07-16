"""ASGI entrypoint for HTTP and same-origin WebSocket traffic."""

import os

from django.core.asgi import get_asgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

django_application = get_asgi_application()

from config.routing import build_protocol_router  # noqa: E402

application = build_protocol_router(django_application)
