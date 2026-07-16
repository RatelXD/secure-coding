from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from apps.catalog.models import Product

User = get_user_model()


def force_login_with_epoch(client: Client, user) -> None:
    client.force_login(user)
    session = client.session
    session["account_auth_epoch"] = user.auth_epoch
    session.save()


class FeatureNavigationTests(TestCase):
    password = "Correct-Horse-Battery-47!"

    def test_home_exposes_public_feature_navigation(self) -> None:
        response = self.client.get(reverse("home"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, reverse("catalog:list"))
        self.assertContains(response, reverse("accounts:user_list"))
        self.assertNotContains(response, reverse("chat:room-list"))

    def test_authenticated_navigation_exposes_chat(self) -> None:
        user = User.objects.create_user(username="nav_user", password=self.password)
        force_login_with_epoch(self.client, user)

        response = self.client.get(reverse("home"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, reverse("chat:room-list"))
        self.assertContains(response, reverse("accounts:profile"))

    def test_non_owner_can_reach_user_and_product_report_forms(self) -> None:
        owner = User.objects.create_user(username="nav_owner", password=self.password)
        reporter = User.objects.create_user(username="nav_reporter", password=self.password)
        product = Product.objects.create(
            owner=owner,
            title="신고 링크 상품",
            description="상품 설명",
            price=10_000,
            image="product-images/navigation.png",
        )
        force_login_with_epoch(self.client, reporter)

        user_response = self.client.get(
            reverse("accounts:user_detail", kwargs={"username": owner.username})
        )
        product_response = self.client.get(
            reverse("catalog:detail", kwargs={"pk": product.pk})
        )

        self.assertContains(
            user_response,
            reverse("moderation:report-user", kwargs={"target_id": owner.pk}),
        )
        self.assertContains(
            product_response,
            reverse("moderation:report-product", kwargs={"target_id": product.pk}),
        )
