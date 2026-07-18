import pytest
from django.db import IntegrityError, transaction
from django.db.models.deletion import ProtectedError
from django.utils import timezone

from apps.accounts.models import (
    RevocationTask,
    RevocationWorkerHeartbeat,
    User,
    UserSessionIndex,
)

pytestmark = pytest.mark.django_db


def test_g7a_withdrawal_model_001_preserves_existing_user_defaults() -> None:
    """G7A-WITHDRAWAL-MODEL-001: 준비 필드는 기존 사용자를 활성 상태로 유지한다."""
    user = User.objects.create_user(
        username="prepared_user",
        password="not-a-real-secret-123",
    )

    assert user.withdrawn_at is None
    assert user.auth_epoch == 0
    assert user.is_active is True


def test_g7a_withdrawal_model_002_indexes_sessions_without_changing_session() -> None:
    """G7A-WITHDRAWAL-MODEL-002: 세션 인덱스는 epoch와 키를 보존하고 중복 키를 거부한다."""
    user = User.objects.create_user(username="session_user", password="unusable")
    indexed = UserSessionIndex.objects.create(
        user=user,
        session_key="a" * 40,
        auth_epoch=user.auth_epoch,
    )

    assert indexed.revoked_at is None
    assert indexed.user_id == user.pk

    with pytest.raises(IntegrityError), transaction.atomic():
        UserSessionIndex.objects.create(
            user=user,
            session_key="a" * 40,
            auth_epoch=user.auth_epoch,
        )

    with pytest.raises(ProtectedError):
        user.delete()


def test_g7a_withdrawal_model_003_revocation_task_is_idempotent_per_epoch() -> None:
    """G7A-WITHDRAWAL-MODEL-003: 같은 사용자·epoch의 outbox task는 최대 한 건이다."""
    user = User.objects.create_user(username="revocation_user", password="unusable")
    task = RevocationTask.objects.create(
        user=user,
        event_key=f"withdrawal:{user.pk}:auth-epoch:1",
        auth_epoch=1,
    )

    assert task.status == RevocationTask.Status.PENDING
    assert task.attempt_count == 0

    with pytest.raises(IntegrityError), transaction.atomic():
        RevocationTask.objects.create(
            user=user,
            event_key=f"account.withdrawn:{user.pk}:1:duplicate",
            auth_epoch=1,
        )


def test_g7a_withdrawal_model_004_rejects_invalid_completion_state() -> None:
    """G7A-WITHDRAWAL-MODEL-004: 성공 시각 없는 완료와 완료 시각 있는 retry를 거부한다."""
    user = User.objects.create_user(username="task_state_user", password="unusable")

    with pytest.raises(IntegrityError), transaction.atomic():
        RevocationTask.objects.create(
            user=user,
            event_key=f"account.withdrawn:{user.pk}:1",
            auth_epoch=1,
            status=RevocationTask.Status.COMPLETED,
        )

    with pytest.raises(IntegrityError), transaction.atomic():
        RevocationTask.objects.create(
            user=user,
            event_key=f"account.withdrawn:{user.pk}:2",
            auth_epoch=2,
            status=RevocationTask.Status.RETRY,
            completed_at=timezone.now(),
        )


def test_g7a_withdrawal_model_005_heartbeat_keeps_failure_visible() -> None:
    """G7A-WITHDRAWAL-MODEL-005: worker heartbeat는 최근 실패를 숨기지 않는다."""
    now = timezone.now()
    heartbeat = RevocationWorkerHeartbeat.objects.create(
        worker_key="revocation-primary",
        heartbeat_at=now,
        last_error="session store unavailable",
    )

    heartbeat.refresh_from_db()
    assert heartbeat.heartbeat_at == now
    assert heartbeat.last_success_at is None
    assert heartbeat.last_error == "session store unavailable"
