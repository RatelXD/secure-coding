from django import forms
from django.contrib.auth.forms import PasswordChangeForm, UserCreationForm

from .models import User
from .validators import canonicalize_username


class SignupForm(UserCreationForm):
    class Meta(UserCreationForm.Meta):
        model = User
        fields = ("username",)

    def clean_username(self) -> str:
        username = canonicalize_username(self.cleaned_data["username"])
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
