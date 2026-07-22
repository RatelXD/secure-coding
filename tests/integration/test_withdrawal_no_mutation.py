import pytest
from django.apps import apps
from django.test import Client

from apps.accounts.models import User

pytestmark = pytest.mark.django_db

LEGACY_WITHDRAWAL_PATHS = (
    "/accounts/withdraw/",
    "/account/delete/",
    "/accounts/delete/",
)


def force_login_with_epoch(client: Client, user: User) -> None:
    client.force_login(user)
    session = client.session
    session["account_auth_epoch"] = user.auth_epoch
    session.save()


def snapshot_accounts_rows() -> dict[str, list[dict[str, object]]]:
    """Capture every accounts-owned row so a rejected request cannot hide side effects."""
    return {
        model._meta.label_lower: list(model.objects.order_by(model._meta.pk.name).values())
        for model in apps.get_app_config("accounts").get_models()
    }


@pytest.mark.parametrize("method", ("get", "post"))
@pytest.mark.parametrize("path", LEGACY_WITHDRAWAL_PATHS)
def test_g7d_withdrawal_003_legacy_paths_are_404_and_write_nothing(
    method: str,
    path: str,
) -> None:
    user = User.objects.create_user(
        username="withdrawal_guard_user",
        password="Correct-Horse-Battery-47!",
        bio="보존해야 하는 소개글",
    )
    client = Client()
    force_login_with_epoch(client, user)
    assert client.get("/account/").status_code == 200
    before = snapshot_accounts_rows()

    response = getattr(client, method)(path, {"confirm": "yes"})

    assert response.status_code == 404
    assert snapshot_accounts_rows() == before


@pytest.mark.parametrize("method, expected", (("get", 200), ("post", 200)))
def test_g7d_withdrawal_004_invalid_activation_request_writes_nothing(
    method: str,
    expected: int,
) -> None:
    user = User.objects.create_user(
        username="withdrawal_active_guard",
        password="Correct-Horse-Battery-47!",
    )
    client = Client()
    force_login_with_epoch(client, user)
    assert client.get("/account/").status_code == 200
    before = snapshot_accounts_rows()

    response = getattr(client, method)("/account/withdraw/", {"confirm": "yes"})

    assert response.status_code == expected
    assert snapshot_accounts_rows() == before
