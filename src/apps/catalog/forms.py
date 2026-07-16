from __future__ import annotations

from django import forms
from django.core.files.base import ContentFile
from django.core.files.uploadedfile import UploadedFile

from .models import Product
from .services import product_image_pipeline


class ProductFieldsForm(forms.ModelForm):
    image = forms.FileField(
        label="상품 이미지",
        help_text="JPEG, PNG, WebP / 최대 5 MiB / 최대 4096×4096",
        required=False,
    )

    class Meta:
        model = Product
        fields = ("title", "description", "price", "sale_state", "image")
        labels = {
            "title": "상품명",
            "description": "설명",
            "price": "가격",
            "sale_state": "판매 상태",
        }
        widgets = {"description": forms.Textarea(attrs={"rows": 6})}

    def clean_image(self) -> ContentFile | None:
        upload = self.cleaned_data.get("image")
        if upload is None:
            return None
        if not isinstance(upload, UploadedFile):
            raise forms.ValidationError("올바른 이미지 파일을 선택해 주세요.")
        sanitized = product_image_pipeline.sanitize(upload=upload)
        return ContentFile(sanitized.content, name=sanitized.storage_name)


class ProductCreateForm(ProductFieldsForm):
    def clean_image(self) -> ContentFile:
        image = super().clean_image()
        if image is None:
            raise forms.ValidationError("상품 이미지는 필수입니다.")
        return image


class ProductUpdateForm(ProductFieldsForm):
    version = forms.IntegerField(min_value=1, widget=forms.HiddenInput)

    class Meta(ProductFieldsForm.Meta):
        pass
