from html.parser import HTMLParser

import pytest
from django.test import Client
from django.urls import reverse

from apps.accounts.models import User

pytestmark = pytest.mark.django_db

FORBIDDEN_TARGET_MARKERS = ("withdraw", "delete", "deactivate", "close-account")


class NavigationTargetParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.targets: list[str] = []

    def handle_starttag(
        self,
        tag: str,
        attrs: list[tuple[str, str | None]],
    ) -> None:
        attribute_name = "href" if tag == "a" else "action" if tag == "form" else None
        if attribute_name is None:
            return
        attributes = dict(attrs)
        target = attributes.get(attribute_name)
        if target is not None:
            self.targets.append(target)


def force_login_with_epoch(client: Client, user: User) -> None:
    client.force_login(user)
    session = client.session
    session["account_auth_epoch"] = user.auth_epoch
    session.save()


@pytest.mark.parametrize(
    "route_name",
    (
        "home",
        "accounts:profile",
        "accounts:bio_edit",
        "accounts:password_change",
    ),
)
def test_g7a_withdrawal_004_authenticated_pages_expose_no_withdrawal_navigation(
    route_name: str,
) -> None:
    """TEST-ID G7A-WITHDRAWAL-004: no authenticated link or form activates withdrawal."""
    user = User.objects.create_user(
        username="withdrawal_nav_user",
        password="Correct-Horse-Battery-47!",
    )
    client = Client()
    force_login_with_epoch(client, user)

    response = client.get(reverse(route_name))

    assert response.status_code == 200
    parser = NavigationTargetParser()
    parser.feed(response.content.decode())
    assert parser.targets
    assert not any(
        marker in target.casefold()
        for target in parser.targets
        for marker in FORBIDDEN_TARGET_MARKERS
    )
    assert "회원 탈퇴" not in response.content.decode()
