from hashlib import sha256
from io import BytesIO

import pytest
from django.core.files.base import ContentFile
from django.core.files.storage import FileSystemStorage
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import transaction
from django.test import Client
from django.urls import reverse
from PIL import Image

from apps.accounts.models import User
from apps.catalog.models import Category, Product, ProductImage
from apps.catalog.services import (
    SanitizedProductImage,
    product_image_pipeline,
    replace_product_images,
)

pytestmark = pytest.mark.django_db


def _png_upload(index: int) -> SimpleUploadedFile:
    output = BytesIO()
    color = (index * 40, 255 - index * 40, index * 20)
    Image.new("RGB", (8, 8), color).save(output, format="PNG")
    return SimpleUploadedFile(
        f"image-{index}.png",
        output.getvalue(),
        content_type="image/png",
    )


def _storage(tmp_path, monkeypatch) -> FileSystemStorage:
    storage = FileSystemStorage(location=tmp_path, base_url="/media/")
    monkeypatch.setattr(ProductImage._meta.get_field("image"), "storage", storage)
    return storage


def _stored_files(tmp_path) -> list:
    return [path for path in tmp_path.rglob("*") if path.is_file()]


def _read_stored_file(storage: FileSystemStorage, name: str) -> bytes:
    with storage.open(name, "rb") as stored:
        return stored.read()



def _login(client: Client, user: User) -> None:
    client.force_login(user)
    session = client.session
    session["account_auth_epoch"] = user.auth_epoch
    session.save()


def _category() -> Category:
    return Category.objects.order_by("display_order").first()


def _create_payload(image_count: int) -> dict[str, object]:
    return {
        "title": f"경계 상품 {image_count}",
        "description": "다중 이미지 경계 검증",
        "price": "10000",
        "category": _category().pk,
        "region": "",
        "images": [_png_upload(index) for index in range(image_count)],
    }


@pytest.mark.parametrize("image_count", [0, 1, 4])
def test_authenticated_create_accepts_zero_one_or_four_ordered_images(
    image_count: int, tmp_path, monkeypatch
) -> None:
    """G7A-CAT-BOUNDARY-001: 0/1/4장은 바이트와 순서를 보존해 허용한다."""
    storage = _storage(tmp_path, monkeypatch)
    owner = User.objects.create_user(
        username=f"owner_{image_count}",
        password="long-password-123",
    )
    client = Client()
    _login(client, owner)
    expected_contents = [
        product_image_pipeline.sanitize(upload=_png_upload(index)).content
        for index in range(image_count)
    ]

    response = client.post(reverse("catalog:create"), _create_payload(image_count))

    assert response.status_code == 302
    product = Product.objects.get(owner=owner)
    images = list(ProductImage.objects.filter(product=product).order_by("position"))
    assert len(images) == image_count
    assert [image.position for image in images] == list(range(image_count))
    assert product.image.name == ""
    assert [image.sha256 for image in images] == [
        sha256(content).hexdigest() for content in expected_contents
    ]
    assert [
        _read_stored_file(storage, image.image.name) for image in images
    ] == expected_contents
    assert all(image.image.name != product.image.name for image in images)


def test_authenticated_create_rejects_five_images_without_partial_rows(
    tmp_path, monkeypatch
) -> None:
    """G7A-CAT-BOUNDARY-002: 5장은 행이나 저장소 잔재 없이 거부한다."""
    _storage(tmp_path, monkeypatch)
    owner = User.objects.create_user(username="owner_five", password="long-password-123")
    client = Client()
    _login(client, owner)

    response = client.post(reverse("catalog:create"), _create_payload(5))

    assert response.status_code == 200
    assert "이미지는 최대 4장" in response.content.decode()
    assert not Product.objects.filter(owner=owner).exists()
    assert not ProductImage.objects.exists()
    assert _stored_files(tmp_path) == []


def test_authenticated_create_storage_failure_leaves_no_orphaned_blobs(
    tmp_path, monkeypatch
) -> None:
    """G7A-CAT-BOUNDARY-003: 단계 저장 실패는 행과 임시 바이트를 모두 정리한다."""
    storage = _storage(tmp_path, monkeypatch)
    owner = User.objects.create_user(username="owner_failure", password="long-password-123")
    client = Client()
    _login(client, owner)
    original_save = storage.save
    saves = 0

    def fail_second_save(name, content, max_length=None):
        nonlocal saves
        saves += 1
        if saves == 2:
            raise OSError("injected storage failure")
        return original_save(name, content, max_length=max_length)

    monkeypatch.setattr(storage, "save", fail_second_save)

    with pytest.raises(OSError, match="injected storage failure"):
        client.post(reverse("catalog:create"), _create_payload(4))

    assert not Product.objects.filter(owner=owner).exists()
    assert not ProductImage.objects.exists()
    assert _stored_files(tmp_path) == []


def test_gallery_creation_never_aliases_or_deletes_legacy_product_image(
    tmp_path, monkeypatch
) -> None:
    """G7A-CAT-BOUNDARY-004: gallery keys do not take ownership of legacy Product.image."""
    storage = _storage(tmp_path, monkeypatch)
    legacy_key = "product-images/legacy/keep.png"
    legacy_bytes = b"legacy-image"
    storage.save(legacy_key, ContentFile(legacy_bytes))
    owner = User.objects.create_user(username="owner_legacy", password="long-password-123")
    product = Product.objects.create(
        owner=owner,
        title="레거시 이미지 상품",
        description="레거시 키 보존 검증",
        price=10_000,
        category=_category(),
        image=legacy_key,
    )
    gallery_bytes = b"new-gallery-image"

    with transaction.atomic():
        replace_product_images(
            product=product,
            images=[
                SanitizedProductImage(
                    storage_name="gallery.png",
                    content_type="image/png",
                    width=1,
                    height=1,
                    byte_size=len(gallery_bytes),
                    content=gallery_bytes,
                )
            ],
        )

    product.refresh_from_db()
    image = ProductImage.objects.get(product=product)
    assert product.image.name == legacy_key
    assert image.image.name != legacy_key
    assert image.owned_key != legacy_key
    assert _read_stored_file(storage, legacy_key) == legacy_bytes


def test_anonymous_gallery_submission_cannot_create_product() -> None:
    """G7A-CAT-AUTHZ-001: 다중 이미지 추가도 기존 인증 경계를 우회하지 못한다."""
    response = Client().post(reverse("catalog:create"), _create_payload(1))

    assert response.status_code == 302
    assert not Product.objects.exists()
    assert not ProductImage.objects.exists()