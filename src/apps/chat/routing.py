from __future__ import annotations

from django.urls.resolvers import URLPattern

# Cycle 1 consumers are introduced only after G2. Keeping the exported routing
# contract empty makes the ASGI skeleton executable without exposing a fake or
# unauthenticated WebSocket endpoint.
websocket_urlpatterns: list[URLPattern] = []
