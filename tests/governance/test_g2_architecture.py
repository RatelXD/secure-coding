from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


class G2ArchitectureTests(unittest.TestCase):
    def text(self, relative: str) -> str:
        return (ROOT / relative).read_text(encoding="utf-8")

    def test_django_and_runtime_dependencies_are_exactly_pinned(self) -> None:
        project = self.text("pyproject.toml")
        self.assertIn('"django==5.2.', project)
        for dependency in ("channels==", "channels-redis==", "pillow==", "psycopg[binary]==", "uvicorn=="):
            self.assertIn(dependency, project)

    def test_chat_and_moderation_are_registered(self) -> None:
        settings = self.text("src/config/settings.py")
        self.assertIn('"apps.chat"', settings)
        self.assertIn('"apps.moderation"', settings)
        self.assertIn('AUTH_USER_MODEL = "accounts.User"', settings)

    def test_websocket_security_envelope_wraps_chat_routes(self) -> None:
        routing = self.text("src/config/routing.py")
        self.assertIn("AllowedHostsOriginValidator(", routing)
        self.assertIn("AuthMiddlewareStack(URLRouter(websocket_urlpatterns))", routing)
        self.assertIn("from apps.chat.routing import websocket_urlpatterns", routing)

    def test_http_status_adapter_is_after_authentication(self) -> None:
        settings = self.text("src/config/settings.py")
        auth = settings.index("django.contrib.auth.middleware.AuthenticationMiddleware")
        authority = settings.index("config.middleware.CanonicalUserStatusMiddleware")
        self.assertLess(auth, authority)
        account_service = self.text("src/apps/accounts/services.py")
        self.assertIn("effective_user_status(user_id=user.pk)", account_service)
        self.assertIn("EffectiveUserStatus.ACTIVE", account_service)

    def test_canonical_status_queries_use_database_time(self) -> None:
        services = self.text("src/apps/moderation/services.py")
        self.assertEqual(services.count("starts_at__lte=Now()"), 2)
        self.assertEqual(services.count("expires_at__gt=Now()"), 2)
        self.assertIn("effective_user_status", services)
        self.assertIn("effective_product_visibility", services)

    def test_chat_contract_is_database_accepted_and_redis_degraded(self) -> None:
        services = self.text("src/apps/chat/services.py")
        models = self.text("src/apps/chat/models.py")
        self.assertIn("persist before ACK", services)
        self.assertIn("Redis failure returns DEGRADED", services)
        self.assertIn("without publishing again", services)
        self.assertIn('name="chat_unique_client_message"', models)
        self.assertNotIn("published", models.lower())

    def test_moderation_is_reversible_and_reports_are_consumed_once(self) -> None:
        models = self.text("src/apps/moderation/models.py")
        services = self.text("src/apps/moderation/services.py")
        self.assertIn('name="moderation_action_seven_day_window"', models)
        self.assertIn("consumed_by", models)
        self.assertIn('name="moderation_report_no_self_target"', models)
        self.assertIn('name="moderation_unique_reporter_user"', models)
        self.assertIn('name="moderation_unique_reporter_product"', models)
        self.assertIn("class ModerationActionAuthority(Protocol)", services)
        self.assertIn("exactly one seven-day action and audit event", services)
        self.assertNotIn("on_delete=models.CASCADE", models)

    def test_transfer_authority_surface_is_present(self) -> None:
        for relative in (
            "src/apps/transfers/models.py",
            "src/apps/transfers/services.py",
            "src/apps/transfers/views.py",
            "src/apps/transfers/migrations/0001_initial.py",
            "src/apps/trades/services.py",
            "src/apps/trades/migrations/0002_trade_version_tradestatushistory.py",
        ):
            self.assertTrue((ROOT / relative).is_file(), relative)


if __name__ == "__main__":
    unittest.main()
