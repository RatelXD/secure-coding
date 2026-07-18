import inspect

from django import forms

from apps.accounts import forms as account_forms
from apps.accounts.urls import urlpatterns


FORBIDDEN_PUBLIC_MARKERS = ("withdraw", "delete", "deactivate", "close-account")


def test_g7a_withdrawal_001_accounts_url_inventory_has_no_withdrawal_surface() -> None:
    """TEST-ID G7A-WITHDRAWAL-001: Phase 7A registers no withdrawal URL."""
    registered_routes = {
        "route": [str(pattern.pattern) for pattern in urlpatterns],
        "name": [pattern.name or "" for pattern in urlpatterns],
    }

    for inventory in registered_routes.values():
        assert not any(
            marker in value.casefold()
            for value in inventory
            for marker in FORBIDDEN_PUBLIC_MARKERS
        )


def test_g7a_withdrawal_002_accounts_form_inventory_has_no_withdrawal_form() -> None:
    """TEST-ID G7A-WITHDRAWAL-002: Phase 7A exports no destructive account form."""
    public_form_names = {
        name
        for name, candidate in inspect.getmembers(account_forms, inspect.isclass)
        if candidate.__module__ == account_forms.__name__
        and issubclass(candidate, forms.BaseForm)
    }

    assert public_form_names
    assert not any(
        marker in form_name.casefold()
        for form_name in public_form_names
        for marker in FORBIDDEN_PUBLIC_MARKERS
    )
