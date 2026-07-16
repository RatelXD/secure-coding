from __future__ import annotations
import logging
from datetime import timedelta
from io import BytesIO, StringIO
from uuid import UUID

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile

from django.contrib.auth import get_user_model
from django.db.models.functions import Now
from django.test import Client, SimpleTestCase, TestCase
from django.urls import reverse
from django.utils import timezone
from PIL import Image
from PIL.PngImagePlugin import PngInfo

from apps.chat.consumers import has_exact_origin
from apps.catalog.models import Product
from apps.catalog.services import product_image_pipeline
from apps.moderation.models import AbuseReport, ModerationAction


User = get_user_model()


def png_bytes(*, metadata_value: str | None = None) -> bytes:
    output = BytesIO()
    metadata = None
    if metadata_value is not None:
        metadata = PngInfo()
        metadata.add_text("private-marker", metadata_value)
    Image.new("RGB", (2, 2), (20, 40, 60)).save(output, format="PNG", pnginfo=metadata)
    return output.getvalue()


class AccountHttpSecurityTests(TestCase):
    strong_password = "Correct-Horse-Battery-47!"

    def test_signup_hashes_password_and_rejects_nul(self) -> None:
        response = self.client.post(
            reverse("accounts:signup"),
            {
                "username": "safe_user",
                "password1": self.strong_password,
                "password2": self.strong_password,
            },
        )

        self.assertEqual(response.status_code, 302)
        user = User.objects.get(username="safe_user")
        self.assertNotEqual(user.password, self.strong_password)
        self.assertNotIn(self.strong_password, user.password)
        self.assertTrue(user.check_password(self.strong_password))

        nul_password = "Valid-looking\x00password-47!"
        rejected = Client().post(
            reverse("accounts:signup"),
            {
                "username": "nul_user",
                "password1": nul_password,
                "password2": nul_password,
            },
        )
        self.assertEqual(rejected.status_code, 200)
        self.assertFalse(User.objects.filter(username="nul_user").exists())

    def test_public_profile_escapes_bio_and_omits_sensitive_fields(self) -> None:
        user = User.objects.create_user(
            username="public_user",
            password=self.strong_password,
            email="private-marker@example.invalid",
            bio='<script data-private="marker">alert(1)</script>',
        )

        response = self.client.get(
            reverse("accounts:user_detail", kwargs={"username": user.username})
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "&lt;script data-private=&quot;marker&quot;&gt;", html=False)
        self.assertNotContains(response, '<script data-private="marker">', html=False)
        self.assertNotContains(response, "private-marker@example.invalid")
        self.assertNotContains(response, user.password)

    def test_anonymous_account_mutations_require_login(self) -> None:
        for route_name in ("accounts:profile", "accounts:bio_edit", "accounts:password_change"):
            with self.subTest(route_name=route_name):
                response = self.client.get(reverse(route_name))
                self.assertEqual(response.status_code, 302)
                self.assertIn(reverse("accounts:login"), response.headers["Location"])

    def test_authenticated_account_mutations_require_csrf(self) -> None:
        user = User.objects.create_user(
            username="csrf_user",
            password=self.strong_password,
        )
        csrf_client = Client(enforce_csrf_checks=True)
        csrf_client.force_login(user)

        requests = (
            ("accounts:bio_edit", {"bio": "changed"}),
            (
                "accounts:password_change",
                {
                    "old_password": self.strong_password,
                    "new_password1": "Another-Safe-Password-47!",
                    "new_password2": "Another-Safe-Password-47!",
                },
            ),
            ("accounts:logout", {}),
        )
        for route_name, data in requests:
            with self.subTest(route_name=route_name):
                response = csrf_client.post(reverse(route_name), data)
                self.assertEqual(response.status_code, 403)

        user.refresh_from_db()
        self.assertEqual(user.bio, "")
        self.assertTrue(user.check_password(self.strong_password))

    def test_login_failure_message_does_not_disclose_account_existence(self) -> None:
        User.objects.create_user(username="known_user", password=self.strong_password)
        expected_message = "아이디 또는 비밀번호를 확인해 주세요. 잠시 후 다시 시도할 수 있습니다."

        unknown = self.client.post(
            reverse("accounts:login"),
            {"username": "missing_user", "password": "Wrong-Password-47!"},
        )
        known = self.client.post(
            reverse("accounts:login"),
            {"username": "known_user", "password": "Wrong-Password-47!"},
        )

        self.assertEqual(unknown.status_code, 200)
        self.assertEqual(known.status_code, 200)
        self.assertContains(unknown, expected_message)
        self.assertContains(known, expected_message)

    def test_login_does_not_write_raw_password_to_logs(self) -> None:
        raw_password = "Logging-Marker-Password-47!"
        stream = StringIO()
        handler = logging.StreamHandler(stream)
        root_logger = logging.getLogger()
        root_logger.addHandler(handler)
        try:
            self.client.post(
                reverse("accounts:login"),
                {"username": "missing_user", "password": raw_password},
            )
        finally:
            root_logger.removeHandler(handler)

        self.assertNotIn(raw_password, stream.getvalue())


class CatalogHttpSecurityTests(TestCase):
    strong_password = AccountHttpSecurityTests.strong_password

    def setUp(self) -> None:
        self.owner = User.objects.create_user(
            username="product_owner",
            password=self.strong_password,
            email="seller-private@example.invalid",
        )
        self.other = User.objects.create_user(
            username="other_user",
            password=self.strong_password,
        )
        self.product = Product.objects.create(
            owner=self.owner,
            title="상품",
            description='<img src=x onerror="alert(1)">',
            price=1000,
            sale_state=Product.SaleState.AVAILABLE,
            image="product-images/example.png",
        )

    def test_anonymous_create_and_non_owner_mutations_are_denied(self) -> None:
        anonymous = self.client.get(reverse("catalog:create"))
        self.assertEqual(anonymous.status_code, 302)
        self.assertIn(reverse("accounts:login"), anonymous.headers["Location"])

        self.client.force_login(self.other)
        for route_name in ("catalog:update", "catalog:delete"):
            with self.subTest(route_name=route_name):
                response = self.client.post(
                    reverse(route_name, kwargs={"pk": self.product.pk}),
                    {"version": self.product.version},
                )
                self.assertEqual(response.status_code, 404)

        self.product.refresh_from_db()
        self.assertEqual(self.product.title, "상품")

    def test_product_mutations_require_csrf(self) -> None:
        csrf_client = Client(enforce_csrf_checks=True)
        csrf_client.force_login(self.owner)

        create = csrf_client.post(
            reverse("catalog:create"),
            {
                "title": "새 상품",
                "description": "설명",
                "price": "1000",
                "sale_state": Product.SaleState.AVAILABLE,
            },
        )
        delete = csrf_client.post(
            reverse("catalog:delete", kwargs={"pk": self.product.pk}),
            {"version": self.product.version},
        )

        self.assertEqual(create.status_code, 403)
        self.assertEqual(delete.status_code, 403)
        self.assertTrue(Product.objects.filter(pk=self.product.pk).exists())

    def test_public_product_escapes_content_and_omits_seller_email(self) -> None:
        response = self.client.get(
            reverse("catalog:detail", kwargs={"pk": self.product.pk})
        )

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, '<img src=x onerror="alert(1)">', html=False)
        self.assertNotContains(response, "seller-private@example.invalid")
        self.assertContains(response, self.owner.username)

    def test_active_hide_is_404_and_expired_hide_restores_visibility(self) -> None:
        active = ModerationAction.objects.create(
            kind=ModerationAction.Kind.PRODUCT_HIDE,
            target_product=self.product,
            expires_at=Now() + timedelta(days=7),
        )
        hidden = self.client.get(
            reverse("catalog:detail", kwargs={"pk": self.product.pk})
        )
        self.assertEqual(hidden.status_code, 404)

        active.delete()
        expired_start = timezone.now() - timedelta(days=8)
        ModerationAction.objects.create(
            kind=ModerationAction.Kind.PRODUCT_HIDE,
            target_product=self.product,
            starts_at=expired_start,
            expires_at=expired_start + timedelta(days=7),
        )
        visible = self.client.get(
            reverse("catalog:detail", kwargs={"pk": self.product.pk})
        )
        self.assertEqual(visible.status_code, 200)


class ProductImageSecurityTests(TestCase):
    def test_sanitizer_removes_metadata_and_uses_uuid_name(self) -> None:
        secret_metadata = "metadata-must-not-survive"
        upload = SimpleUploadedFile(
            "camera.png",
            png_bytes(metadata_value=secret_metadata),
            content_type="image/png",
        )

        sanitized = product_image_pipeline.sanitize(upload=upload)

        stem, extension = sanitized.storage_name.rsplit(".", 1)
        self.assertEqual(UUID(stem).version, 4)
        self.assertEqual(extension, "png")
        self.assertNotIn(secret_metadata.encode(), sanitized.content)
        with Image.open(BytesIO(sanitized.content)) as image:
            image.load()
            self.assertEqual(image.format, "PNG")
            self.assertNotIn("private-marker", image.info)

    def test_sanitizer_rejects_svg_polyglot_corruption_and_paths(self) -> None:
        valid_png = png_bytes()
        path_upload = SimpleUploadedFile(
            "safe.png",
            valid_png,
            content_type="image/png",
        )
        path_upload._name = "../escape.png"
        cases = (
            SimpleUploadedFile(
                "image.png",
                b'<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>',
                content_type="image/png",
            ),
            SimpleUploadedFile(
                "polyglot.png",
                valid_png + b"<script>alert(1)</script>",
                content_type="image/png",
            ),
            SimpleUploadedFile(
                "corrupt.png",
                valid_png[:20],
                content_type="image/png",
            ),
            path_upload,
        )

        for upload in cases:
            with self.subTest(upload=upload.name):
                with self.assertRaises(ValidationError):
                    product_image_pipeline.sanitize(upload=upload)


class ModerationHttpSecurityTests(TestCase):
    strong_password = AccountHttpSecurityTests.strong_password

    def setUp(self) -> None:
        old_joined_at = timezone.now() - timedelta(days=8)
        self.reporter = User.objects.create_user(
            username="http_reporter",
            password=self.strong_password,
        )
        self.target = User.objects.create_user(
            username="http_target",
            password=self.strong_password,
        )
        User.objects.filter(pk=self.reporter.pk).update(date_joined=old_joined_at)
        self.reporter.refresh_from_db()
        self.product = Product.objects.create(
            owner=self.target,
            title="신고 HTTP 대상",
            description="설명",
            price=1000,
            sale_state=Product.SaleState.AVAILABLE,
            image="product-images/report.png",
        )

    def test_report_entrypoints_require_authentication_and_csrf(self) -> None:
        user_route = reverse(
            "moderation:report-user",
            kwargs={"target_id": self.target.pk},
        )
        anonymous = self.client.get(user_route)
        self.assertEqual(anonymous.status_code, 302)
        self.assertIn(reverse("accounts:login"), anonymous.headers["Location"])

        csrf_client = Client(enforce_csrf_checks=True)
        csrf_client.force_login(self.reporter)
        product_route = reverse(
            "moderation:report-product",
            kwargs={"target_id": self.product.pk},
        )
        rejected = csrf_client.post(product_route, {"reason": "사유"})
        self.assertEqual(rejected.status_code, 403)
        self.assertFalse(AbuseReport.objects.exists())

    def test_reason_is_required_and_self_report_uses_generic_error(self) -> None:
        self.client.force_login(self.reporter)
        product_route = reverse(
            "moderation:report-product",
            kwargs={"target_id": self.product.pk},
        )
        missing_reason = self.client.post(product_route, {"reason": ""})
        self.assertEqual(missing_reason.status_code, 400)
        self.assertFalse(AbuseReport.objects.exists())

        self_route = reverse(
            "moderation:report-user",
            kwargs={"target_id": self.reporter.pk},
        )
        self_report = self.client.post(
            self_route,
            {"context": "PROFILE", "reason": "자기 신고"},
        )
        self.assertEqual(self_report.status_code, 400)
        self.assertContains(
            self_report,
            "신고를 처리할 수 없습니다. 입력 내용을 확인해 주세요.",
            status_code=400,
        )
        self.assertFalse(AbuseReport.objects.exists())


class WebSocketAndClientSecurityTests(SimpleTestCase):
    def test_websocket_origin_must_match_scheme_host_and_port_exactly(self) -> None:
        valid_scope = {
            "scheme": "wss",
            "headers": [
                (b"host", b"market.example:443"),
                (b"origin", b"https://market.example"),
            ],
        }
        self.assertTrue(has_exact_origin(valid_scope))

        invalid_scopes = (
            {"scheme": "wss", "headers": [(b"host", b"market.example")]},
            {
                "scheme": "wss",
                "headers": [
                    (b"host", b"market.example"),
                    (b"origin", b"http://market.example"),
                ],
            },
            {
                "scheme": "wss",
                "headers": [
                    (b"host", b"market.example"),
                    (b"origin", b"https://sub.market.example"),
                ],
            },
            {
                "scheme": "wss",
                "headers": [
                    (b"host", b"market.example"),
                    (b"origin", b"https://market.example:444"),
                ],
            },
            {
                "scheme": "wss",
                "headers": [
                    (b"host", b"attacker@market.example"),
                    (b"origin", b"https://market.example"),
                ],
            },
            {
                "scheme": "wss",
                "headers": [
                    (b"host", b"market.example"),
                    (b"origin", b"https://market.example"),
                    (b"origin", b"https://market.example"),
                ],
            },
        )
        for scope in invalid_scopes:
            with self.subTest(scope=scope):
                self.assertFalse(has_exact_origin(scope))

    def test_chat_client_renders_untrusted_fields_as_text(self) -> None:
        client_script = (
            settings.BASE_DIR
            / "src"
            / "apps"
            / "chat"
            / "static"
            / "chat"
            / "chat.js"
        ).read_text(encoding="utf-8")

        self.assertIn("sender.textContent", client_script)
        self.assertIn("text.textContent", client_script)
        self.assertNotIn("innerHTML", client_script)
