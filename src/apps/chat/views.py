from __future__ import annotations

from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.db.models import Q
from django.http import Http404, HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import redirect, render
from django.views.decorators.http import require_GET, require_POST

from apps.accounts.services import project_account_identity
from .models import ChatMessage, ProductConversation, Room
from .services import (
    ChatAuthorizationError,
    DefaultChatService,
    _require_active_user,
    _require_room_access,
    get_or_create_product_conversation,
)


@login_required
@require_GET
def room_list(request: HttpRequest) -> HttpResponse:
    global_room = Room.objects.filter(kind=Room.Kind.GLOBAL).first()

    direct_rooms = (
        Room.objects.filter(kind=Room.Kind.DIRECT)
        .filter(Q(direct_user_low=request.user) | Q(direct_user_high=request.user))
        .select_related("direct_user_low", "direct_user_high")
        .order_by("-created_at")
    )
    product_rooms = (
        ProductConversation.objects.filter(
            Q(seller=request.user) | Q(buyer=request.user)
        )
        .select_related("room", "product", "seller", "buyer")
        .order_by("-created_at")
    )
    room_rows = []
    for room in direct_rooms:
        other_user = (
            room.direct_user_high
            if room.direct_user_low_id == request.user.pk
            else room.direct_user_low
        )
        room_rows.append(
            {
                "room": room,
                "other_identity": project_account_identity(user=other_user),
            }
        )
    return render(
        request,
        "chat/room_list.html",
        {
            "global_room": global_room,
            "direct_rooms": room_rows,
            "product_rooms": product_rooms,
        },
    )


@login_required
@require_POST
def product_room(request: HttpRequest, product_id: int) -> HttpResponse:
    try:
        conversation = get_or_create_product_conversation(
            product_id=product_id,
            actor_id=request.user.pk,
        )
    except ChatAuthorizationError as exc:
        raise Http404 from exc
    return redirect("chat:room-detail", room_id=conversation.room_id)


@login_required
@require_GET
def room_detail(request: HttpRequest, room_id: int) -> HttpResponse:
    try:
        with transaction.atomic():
            _require_active_user(user_id=request.user.pk, lock=True)
            room = _require_room_access(
                room_id=room_id,
                user_id=request.user.pk,
                lock=True,
            )
            messages = list(
                ChatMessage.objects.filter(room=room)
                .select_related("sender")
                .order_by("-pk")[:100]
            )
    except ChatAuthorizationError as exc:
        raise Http404 from exc
    messages.reverse()
    chat_messages = [
        {
            "message": message,
            "sender_identity": project_account_identity(user=message.sender),
        }
        for message in messages
    ]
    conversation = (
        ProductConversation.objects.filter(room=room)
        .select_related("product", "seller", "buyer")
        .first()
    )
    global_room = Room.objects.filter(kind=Room.Kind.GLOBAL).first()
    direct_rooms = (
        Room.objects.filter(kind=Room.Kind.DIRECT)
        .filter(Q(direct_user_low=request.user) | Q(direct_user_high=request.user))
        .select_related("direct_user_low", "direct_user_high")
        .order_by("-created_at")
    )
    sidebar_direct_rooms = []
    for direct_room in direct_rooms:
        other_user = (
            direct_room.direct_user_high
            if direct_room.direct_user_low_id == request.user.pk
            else direct_room.direct_user_low
        )
        sidebar_direct_rooms.append(
            {
                "room": direct_room,
                "other_identity": project_account_identity(user=other_user),
            }
        )
    product_rooms = (
        ProductConversation.objects.filter(
            Q(seller=request.user) | Q(buyer=request.user)
        )
        .select_related("room", "product", "seller", "buyer")
        .order_by("-created_at")
    )
    return render(
        request,
        "chat/room_detail.html",
        {
            "room": room,
            "chat_messages": chat_messages,
            "conversation": conversation,
            "global_room": global_room,
            "direct_rooms": sidebar_direct_rooms,
            "product_rooms": product_rooms,
        },
    )


@login_required
@require_GET
def room_history(request: HttpRequest, room_id: int) -> JsonResponse:
    try:
        cursor = int(request.GET.get("cursor", "0"))
        messages = DefaultChatService().history_after(
            room_id=room_id,
            requesting_user_id=request.user.pk,
            cursor=cursor,
            limit=100,
        )
    except (ValueError, ChatAuthorizationError) as exc:
        raise Http404 from exc
    return JsonResponse(
        {
            "messages": [
                {
                    "server_message_id": item.server_message_id,
                    "sender_id": item.sender_id,
                    "sender_username": item.sender_username,
                    "body": item.body,
                    "accepted_at": item.accepted_at.isoformat(),
                }
                for item in messages
            ]
        }
    )
