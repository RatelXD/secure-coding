from __future__ import annotations

from django import forms

from .models import AbuseReport
from .policies import ReportContext, USER_CONTEXTS


class ReportReasonForm(forms.Form):
    reason = forms.CharField(
        label="신고 사유",
        min_length=1,
        max_length=1_000,
        strip=True,
        widget=forms.Textarea(attrs={"rows": 5, "maxlength": 1000}),
    )

    def clean_reason(self) -> str:
        reason = self.cleaned_data["reason"]
        if "\x00" in reason or any(ord(character) < 32 and character != "\n" for character in reason):
            raise forms.ValidationError("신고 사유에 허용되지 않는 문자가 있습니다.")
        return reason


class UserReportForm(ReportReasonForm):
    context = forms.ChoiceField(
        label="신고 맥락",
        choices=[
            (context.value, AbuseReport.Context(context.value).label)
            for context in ReportContext
            if context in USER_CONTEXTS
        ],
    )
