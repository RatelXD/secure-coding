from __future__ import annotations

from django.urls import path
from django.urls.resolvers import URLPattern, URLResolver

from .consumers import ChatConsumer

websocket_urlpatterns: list[URLPattern | URLResolver] = [
    path("ws/chat/rooms/<int:room_id>/", ChatConsumer.as_asgi(), name="chat-room-socket"),
]
