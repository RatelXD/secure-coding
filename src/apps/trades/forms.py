from django import forms


class ReviewForm(forms.Form):
    rating = forms.TypedChoiceField(
        label="평점",
        choices=((value, str(value)) for value in range(1, 6)),
        coerce=int,
    )
    body = forms.CharField(
        label="후기",
        min_length=1,
        max_length=1_000,
        strip=True,
        widget=forms.Textarea(attrs={"rows": 5, "maxlength": 1000}),
    )
