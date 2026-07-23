from __future__ import annotations

from datetime import timedelta
from decimal import Decimal
from uuid import uuid4

from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from django.db import connection
from django.test import Client, RequestFactory, TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone

from apps.catalog.models import Product
from apps.chat.models import ProductConversation, Room
from apps.notifications.context_processors import unread_notification_count
from apps.notifications.models import Notification
from apps.notifications.services import TransferNotification, create_transfer_notifications
from apps.transfers.services import transfer_for_product_room


def force_login_with_epoch(client: Client, user) -> None:
    client.force_login(user)
    session = client.session
    session["account_auth_epoch"] = user.auth_epoch
    session.save()


class NotificationInboxTests(TestCase):
    password = "Correct-Horse-Battery-47!"

    def setUp(self) -> None:
        user_model = get_user_model()
        self.sender = user_model.objects.create_user(username="notice_sender", password=self.password)
        self.recipient = user_model.objects.create_user(
            username="notice_recipient", password=self.password
        )
        self.outsider = user_model.objects.create_user(
            username="notice_outsider", password=self.password
        )

    def test_unread_context_is_zero_for_anonymous_request(self) -> None:
        # Given: an anonymous browser request.
        # When: the shared header context is built.
        # Then: it has no unread count to expose.
        request = RequestFactory().get("/")
        request.user = AnonymousUser()
        with CaptureQueriesContext(connection) as queries:
            context = unread_notification_count(request)

        self.assertEqual(context, {"unread_notification_count": 0})
        self.assertEqual(len(queries), 0)

    def test_unread_context_uses_one_count_query_for_an_authenticated_request(self) -> None:
        # Given: an authenticated user with one unread notification.
        Notification.objects.create(
            recipient=self.recipient,
            event_key="context:unread",
            kind="TEST",
            payload={},
        )
        request = RequestFactory().get("/")
        request.user = self.recipient

        # When: the shared header context is built.
        with CaptureQueriesContext(connection) as queries:
            context = unread_notification_count(request)

        # Then: it returns the current user's count using one bounded database query.
        self.assertEqual(context, {"unread_notification_count": 1})
        self.assertEqual(len(queries), 1)

    def test_header_badge_counts_only_current_unexpired_unread_notifications(self) -> None:
        # Given: one unread, one read, and one expired notification for the current user.
        Notification.objects.create(
            recipient=self.recipient,
            event_key="header:unread",
            kind="TEST",
            payload={},
        )
        Notification.objects.create(
            recipient=self.recipient,
            event_key="header:read",
            kind="TEST",
            payload={},
            read_at=timezone.now(),
        )
        expired = Notification.objects.create(
            recipient=self.recipient,
            event_key="header:expired",
            kind="TEST",
            payload={},
        )
        Notification.objects.filter(pk=expired.pk).update(
            expires_at=timezone.now() - timedelta(seconds=1)
        )
        client = Client()
        force_login_with_epoch(client, self.recipient)

        # When: the authenticated user visits a shared-layout page.
        response = client.get(reverse("home"))

        # Then: the badge announces only the one visible unread notification.
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'aria-label="알림 1개"')

    def test_transfer_notices_render_minimal_safe_details_without_payload_links(self) -> None:
        # Given: a completed transfer's durable sender and recipient notifications.
        transfer_id = uuid4()
        create_transfer_notifications(
            transfer_notification=TransferNotification(
                sender_id=self.sender.pk,
                recipient_id=self.recipient.pk,
                transfer_id=transfer_id,
                amount=Decimal("25.00"),
            )
        )
        client = Client()
        force_login_with_epoch(client, self.recipient)

        # When: the recipient opens the inbox.
        response = client.get(reverse("notifications:inbox"))

        # Then: the message uses the server-derived amount and no untrusted payload URL.
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "notice_sender님에게")
        self.assertContains(response, "25.00")
        self.assertNotContains(response, str(transfer_id))
        self.assertNotContains(response, "https://")

    def test_inbox_hides_other_users_payload_and_read_endpoint_does_not_mutate_it(self) -> None:
        # Given: a recipient-owned row containing a hostile-looking payload.
        notification = Notification.objects.create(
            recipient=self.recipient,
            event_key="private:payload",
            kind="TEST",
            payload={"message": "<script>leak</script>", "url": "https://attacker.invalid"},
        )
        client = Client()
        force_login_with_epoch(client, self.outsider)

        # When: another signed-in user opens their inbox and tries to mark that row read.
        inbox = client.get(reverse("notifications:inbox"))
        read = client.post(reverse("notifications:read", args=(notification.pk,)))

        # Then: neither the private payload nor the read-state is exposed or mutated.
        self.assertEqual(inbox.status_code, 200)
        self.assertNotContains(inbox, "leak")
        self.assertNotContains(inbox, "attacker.invalid")
        self.assertEqual(read.status_code, 404)
        notification.refresh_from_db()
        self.assertIsNone(notification.read_at)

    def test_recipient_read_updates_row_and_removes_header_badge(self) -> None:
        # Given: the recipient has one unread notification.
        notification = Notification.objects.create(
            recipient=self.recipient,
            event_key="read:recipient",
            kind="TEST",
            payload={},
        )
        client = Client()
        force_login_with_epoch(client, self.recipient)

        # When: the recipient submits the read form.
        response = client.post(reverse("notifications:read", args=(notification.pk,)), follow=True)

        # Then: the durable read state and visible unread count are both updated.
        self.assertEqual(response.status_code, 200)
        notification.refresh_from_db()
        self.assertIsNotNone(notification.read_at)
        self.assertNotContains(response, 'aria-label="알림 1개"')

    def test_expired_notification_cannot_be_read_or_counted(self) -> None:
        # Given: an unread row whose database expiry is already in the past.
        notification = Notification.objects.create(
            recipient=self.recipient,
            event_key="read:expired",
            kind="TEST",
            payload={},
        )
        Notification.objects.filter(pk=notification.pk).update(
            expires_at=timezone.now() - timedelta(seconds=1)
        )
        client = Client()
        force_login_with_epoch(client, self.recipient)

        # When: the recipient submits the stale read form.
        response = client.post(reverse("notifications:read", args=(notification.pk,)))

        # Then: neither the durable read state nor the header count can be changed.
        self.assertEqual(response.status_code, 404)
        notification.refresh_from_db()
        self.assertIsNone(notification.read_at)
        self.assertNotContains(client.get(reverse("home")), 'aria-label="알림 1개"')

    def test_product_room_transfer_updates_each_users_badge_inbox_and_read_state(self) -> None:
        # Given: two users in a server-owned product room.
        product = Product.objects.create(
            owner=self.sender,
            title="알림 검증 상품",
            description="알림 검증 설명",
            price=2500,
        )
        room = Room.objects.create(kind=Room.Kind.PRODUCT)
        ProductConversation.objects.create(
            room=room,
            product=product,
            seller=self.sender,
            buyer=self.recipient,
        )

        # When: the sender completes a room-scoped transfer.
        result = transfer_for_product_room(
            sender_user=self.sender,
            room_id=room.pk,
            amount=Decimal("25.00"),
            key=uuid4(),
        )
        sender_client = Client()
        recipient_client = Client()
        force_login_with_epoch(sender_client, self.sender)
        force_login_with_epoch(recipient_client, self.recipient)
        sender_home = sender_client.get(reverse("home"))
        recipient_inbox = recipient_client.get(reverse("notifications:inbox"))

        # Then: each party sees only their own notice and the recipient can clear theirs.
        self.assertEqual(result.status, 201)
        self.assertContains(sender_home, 'aria-label="알림 1개"')
        self.assertContains(recipient_inbox, "notice_sender님에게 25.00원을 받았습니다")
        received = Notification.objects.get(recipient=self.recipient, kind="TRANSFER_RECEIVED")
        read = recipient_client.post(reverse("notifications:read", args=(received.pk,)), follow=True)
        self.assertEqual(read.status_code, 200)
        self.assertNotContains(read, 'aria-label="알림 1개"')

    def test_malformed_payload_renders_a_generic_notice_without_a_link(self) -> None:
        # Given: a legacy or malformed notification payload.
        Notification.objects.create(
            recipient=self.recipient,
            event_key="malformed:payload",
            kind="TRANSFER_RECEIVED",
            payload=["not", "a", "mapping"],
        )
        client = Client()
        force_login_with_epoch(client, self.recipient)

        # When: the recipient loads the inbox.
        response = client.get(reverse("notifications:inbox"))

        # Then: it remains readable without serializing an arbitrary payload or navigation target.
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "송금 알림이 도착했습니다.")
        self.assertNotContains(response, "not", html=True)
