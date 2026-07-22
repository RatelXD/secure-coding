from django import forms
from django.contrib.auth.forms import PasswordChangeForm, UserCreationForm

from .models import User
from .validators import canonicalize_username


class SignupForm(UserCreationForm):
    class Meta(UserCreationForm.Meta):
        model = User
        fields = ("username",)
        labels = {"username": "아이디"}
        help_texts = {"username": "4~30자의 영문 소문자, 숫자 또는 밑줄만 사용할 수 있습니다."}

    def clean_username(self) -> str:
        try:
            username = canonicalize_username(self.cleaned_data["username"])
        except forms.ValidationError as exc:
            raise forms.ValidationError(
                "아이디는 4~30자의 영문 소문자, 숫자 또는 밑줄만 사용할 수 있습니다.",
                code="invalid_username",
            ) from exc
        if User.objects.filter(username=username).exists():
            raise forms.ValidationError("사용할 수 없는 아이디입니다.", code="duplicate_username")
        return username


class LoginForm(forms.Form):
    username = forms.CharField(max_length=128, label="아이디")
    password = forms.CharField(
        max_length=128,
        label="비밀번호",
        strip=False,
        widget=forms.PasswordInput,
    )


class BioForm(forms.ModelForm):
    class Meta:
        model = User
        fields = ("bio",)
        labels = {"bio": "소개글"}
        widgets = {"bio": forms.Textarea(attrs={"rows": 5, "maxlength": 500})}


class OwnPasswordChangeForm(PasswordChangeForm):
    """Django's password validation plus the fixed project-wide bounds."""


class WithdrawalForm(forms.Form):
    password = forms.CharField(
        max_length=128,
        label="현재 비밀번호",
        strip=False,
        widget=forms.PasswordInput,
    )

    def clean(self):
        cleaned = super().clean()
        if set(self.data) - {"password", "csrfmiddlewaretoken"}:
            raise forms.ValidationError("허용되지 않은 입력이 포함되어 있습니다.")
        return cleaned
