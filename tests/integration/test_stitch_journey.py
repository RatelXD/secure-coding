from __future__ import annotations

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from apps.catalog.models import Category, Product

User = get_user_model()


def force_login_with_epoch(client: Client, user) -> None:
    client.force_login(user)
    session = client.session
    session["account_auth_epoch"] = user.auth_epoch
    session.save()


class StitchJourneyTests(TestCase):
    password = "Correct-Horse-Battery-47!"

    def setUp(self) -> None:
        self.seller = User.objects.create_user(
            username="stitch_seller", password=self.password, bio="안전한 거래를 선호합니다."
        )
        self.buyer = User.objects.create_user(
            username="stitch_buyer", password=self.password
        )
        self.product = Product.objects.create(
            owner=self.seller,
            title="Stitch 연결 상품",
            description="사용자 여정 확인 상품",
            price=12000,
        )

    def test_home_connects_categories_latest_products_and_global_search(self) -> None:
        response = self.client.get(reverse("home"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, reverse("catalog:detail", args=(self.product.pk,)))
        self.assertContains(response, 'role="search"')
        for code in Category.objects.values_list("code", flat=True):
            self.assertContains(response, f"?category={code}")
        self.assertNotContains(response, "https://")
        self.assertNotContains(response, "http://")

    def test_public_profile_connects_authorized_chat_and_product_cards(self) -> None:
        force_login_with_epoch(self.client, self.buyer)

        response = self.client.get(
            reverse("accounts:user_detail", kwargs={"username": self.seller.username})
        )

        self.assertContains(response, reverse("chat:room-list"))
        self.assertContains(response, f'value="{self.seller.username}"')
        self.assertContains(response, reverse("catalog:detail", args=(self.product.pk,)))
        self.assertContains(
            response,
            reverse("moderation:report-user", kwargs={"target_id": self.seller.pk}),
        )

    def test_own_profile_exposes_only_live_server_routes(self) -> None:
        force_login_with_epoch(self.client, self.buyer)

        response = self.client.get(reverse("accounts:profile"))

        for route in (
            reverse("accounts:bio_edit"),
            reverse("accounts:password_change"),
            reverse("catalog:favorites"),
            reverse("notifications:inbox"),
            reverse("chat:room-list"),
            reverse("accounts:withdraw"),
        ):
            self.assertContains(response, route)
        self.assertNotContains(response, "/management/")
        self.assertNotContains(response, 'href="#"')

    def test_empty_filter_and_not_found_states_are_actionable_and_generic(self) -> None:
        response = self.client.get(reverse("catalog:list"), {"q": "결과가없는검색어"})
        self.assertContains(response, "조건에 맞는 상품이 없습니다")
        self.assertContains(response, reverse("catalog:list"))

        missing = self.client.get("/private-object-that-does-not-exist/")
        self.assertEqual(missing.status_code, 404)
        self.assertContains(missing, "페이지를 찾을 수 없습니다", status_code=404)
        self.assertNotContains(
            missing,
            "private-object-that-does-not-exist",
            status_code=404,
        )

    def test_gallery_and_room_filter_use_local_keyboard_controls(self) -> None:
        force_login_with_epoch(self.client, self.buyer)
        detail = self.client.get(reverse("catalog:detail", args=(self.product.pk,)))
        rooms = self.client.get(reverse("chat:room-list"))

        self.assertNotContains(detail, 'href="#"')
        self.assertContains(rooms, "data-room-filter")
        self.assertContains(rooms, "data-room-filter-status")
        self.assertContains(detail, "/static/journey.js")
