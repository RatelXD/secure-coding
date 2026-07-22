from django import forms

from apps.accounts import forms as account_forms
from apps.accounts.urls import urlpatterns

def test_g7d_withdrawal_001_registers_only_the_approved_surface() -> None:
    registered = {
        (str(pattern.pattern), pattern.name or "")
        for pattern in urlpatterns
        if "withdraw" in str(pattern.pattern) or "withdraw" in (pattern.name or "")
    }
    assert registered == {("account/withdraw/", "withdraw")}


def test_g7d_withdrawal_002_exports_current_password_form() -> None:
    assert issubclass(account_forms.WithdrawalForm, forms.BaseForm)
    assert tuple(account_forms.WithdrawalForm.base_fields) == ("password",)
    assert isinstance(
        account_forms.WithdrawalForm.base_fields["password"].widget,
        forms.PasswordInput,
    )
