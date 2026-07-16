from __future__ import annotations

from django import forms

from apps.accounts.models import User
from apps.accounts.validators import canonicalize_username
from apps.moderation.services import EffectiveUserStatus, effective_user_status


class DirectRoomForm(forms.Form):
    username = forms.CharField(max_length=30, label="대화 상대 사용자명")

    def __init__(self, *args: object, actor: User, **kwargs: object) -> None:
        super().__init__(*args, **kwargs)
        self.actor = actor
        self.target_user: User | None = None

    def clean_username(self) -> str:
        try:
            username = canonicalize_username(self.cleaned_data["username"])
            target = User.objects.get(username=username, is_active=True)
        except (ValueError, User.DoesNotExist) as exc:
            raise forms.ValidationError("대화 상대를 확인할 수 없습니다.") from exc
        if target.pk == self.actor.pk:
            raise forms.ValidationError("자기 자신과 1대1 대화를 만들 수 없습니다.")
        if effective_user_status(user_id=target.pk) is not EffectiveUserStatus.ACTIVE:
            raise forms.ValidationError("대화 상대를 확인할 수 없습니다.")
        self.target_user = target
        return username
