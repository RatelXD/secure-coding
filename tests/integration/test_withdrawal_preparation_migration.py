from datetime import timedelta

import pytest
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.utils import timezone

pytestmark = pytest.mark.django_db(transaction=True)

ACCOUNTS_BEFORE = ("accounts", "0003_loginthrottle_accounts_login_updated_idx")
ACCOUNTS_AFTER = ("accounts", "0004_withdrawal_preparation")


def test_g7a_withdrawal_migration_001_preserves_users_and_sessions() -> None:
    """G7A-WITHDRAWAL-MIG-001: expand migration은 기존 사용자·세션을 변경하지 않는다."""
    executor = MigrationExecutor(connection)
    original_leaves = executor.loader.graph.leaf_nodes()
    before_targets = [
        ACCOUNTS_BEFORE if app_label == "accounts" else (app_label, migration_name)
        for app_label, migration_name in original_leaves
    ]

    try:
        executor.migrate(before_targets)
        before_apps = executor.loader.project_state(before_targets).apps
        UserBefore = before_apps.get_model("accounts", "User")
        SessionBefore = before_apps.get_model("sessions", "Session")
        user = UserBefore.objects.create(
            username="migration_user",
            password="unusable",
            auth_epoch=0,
        )
        session = SessionBefore.objects.create(
            session_key="m" * 40,
            session_data="opaque-existing-session",
            expire_date=timezone.now() + timedelta(days=1),
        )

        executor = MigrationExecutor(connection)
        after_targets = [
            ACCOUNTS_AFTER if app_label == "accounts" else (app_label, migration_name)
            for app_label, migration_name in original_leaves
        ]
        executor.migrate(after_targets)
        after_apps = executor.loader.project_state(after_targets).apps
        UserAfter = after_apps.get_model("accounts", "User")
        SessionAfter = after_apps.get_model("sessions", "Session")
        UserSessionIndex = after_apps.get_model("accounts", "UserSessionIndex")
        RevocationTask = after_apps.get_model("accounts", "RevocationTask")

        migrated_user = UserAfter.objects.get(pk=user.pk)
        migrated_session = SessionAfter.objects.get(pk=session.pk)
        assert migrated_user.username == "migration_user"
        assert migrated_user.auth_epoch == 0
        assert migrated_user.withdrawn_at is None
        assert migrated_session.session_data == "opaque-existing-session"
        assert UserSessionIndex.objects.count() == 0
        assert RevocationTask.objects.count() == 0
    finally:
        MigrationExecutor(connection).migrate(original_leaves)
