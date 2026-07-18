from __future__ import annotations

from django import forms
from django.core.files.uploadedfile import UploadedFile

from .models import CATEGORY_CHOICES, Category, Product
from .services import SanitizedProductImage, product_image_pipeline

MAX_PRODUCT_IMAGES = 4


class MultipleFileInput(forms.ClearableFileInput):
    allow_multiple_selected = True


class ProductImagesField(forms.FileField):
    widget = MultipleFileInput

    def clean(
        self,
        data: UploadedFile | list[UploadedFile] | tuple[UploadedFile, ...] | None,
        initial: object = None,
    ) -> list[SanitizedProductImage]:
        if data in self.empty_values:
            return []
        uploads = list(data) if isinstance(data, (list, tuple)) else [data]
        if len(uploads) > MAX_PRODUCT_IMAGES:
            raise forms.ValidationError("상품 이미지는 최대 4장까지 등록할 수 있습니다.")

        sanitized: list[SanitizedProductImage] = []
        for upload in uploads:
            if not isinstance(upload, UploadedFile):
                raise forms.ValidationError("올바른 이미지 파일을 선택해 주세요.")
            sanitized.append(product_image_pipeline.sanitize(upload=upload))
        return sanitized


class ProductFieldsForm(forms.ModelForm):
    images = ProductImagesField(
        label="상품 이미지",
        help_text="선택 사항, 최대 4장 / JPEG, PNG, WebP / 장당 5 MiB / 최대 4096×4096",
        required=False,
    )

    class Meta:
        model = Product
        fields = ("title", "description", "price", "category", "region", "images")
        labels = {
            "title": "상품명",
            "description": "설명",
            "price": "가격",
            "category": "분류",
            "region": "거래 지역",
        }
        widgets = {"description": forms.Textarea(attrs={"rows": 6})}
    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        category_field = self.fields["category"]
        category_field.required = False
        category_field.queryset = Category.objects.filter(
            code__in=[code for code, _label in CATEGORY_CHOICES]
        )

    def clean_category(self) -> Category:
        category = self.cleaned_data.get("category")
        if category is not None:
            return category
        try:
            return Category.objects.get(code="OTHER")
        except Category.DoesNotExist as exc:
            raise forms.ValidationError("기타 분류 기준값을 찾을 수 없습니다.") from exc




class ProductCreateForm(ProductFieldsForm):
    pass


class ProductUpdateForm(ProductFieldsForm):
    version = forms.IntegerField(min_value=1, widget=forms.HiddenInput)
    clear_images = forms.BooleanField(
        label="등록된 이미지를 모두 삭제",
        required=False,
    )

    def clean(self) -> dict[str, object]:
        cleaned_data = super().clean()
        if cleaned_data.get("clear_images") and cleaned_data.get("images"):
            self.add_error("clear_images", "새 이미지를 등록할 때는 전체 삭제를 함께 선택할 수 없습니다.")
        return cleaned_data

    class Meta(ProductFieldsForm.Meta):
        pass
