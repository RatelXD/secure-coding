import hashlib
from io import BytesIO

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import DatabaseError, connection, transaction
from PIL import Image

from apps.accounts.models import User
from apps.catalog.models import Category, Product, ProductImage

pytestmark = pytest.mark.django_db


def _png_bytes() -> bytes:
    output = BytesIO()
    Image.new("RGB", (8, 8), "blue").save(output, format="PNG")
    return output.getvalue()


def _product_with_copy() -> tuple[Product, ProductImage]:
    owner = User.objects.create_user(username="guard_owner", password="long-password-123")
    product = Product.objects.create(
        owner=owner,
        title="동결 권위 상품",
        description="old-app 변경 거부 검증",
        price=10_000,
        category=Category.objects.get(pk="OTHER"),
        image="product-images/legacy-source.png",
    )
    payload = _png_bytes()
    copied = ProductImage.objects.create(
        product=product,
        image=SimpleUploadedFile("copy.png", payload, content_type="image/png"),
        position=0,
        sha256=hashlib.sha256(payload).hexdigest(),
        byte_size=len(payload),
        width=8,
        height=8,
    )
    return product, copied


def test_direct_sale_state_write_is_rejected_by_database_authority() -> None:
    """G7A-CAT-GUARD-001: old/new app 모두 sale_state lifecycle 직접 쓰기를 못 한다."""
    product, copied = _product_with_copy()

    with pytest.raises(
        DatabaseError, match="Product.sale_state is frozen; Trade is lifecycle authority"
    ), transaction.atomic():
        Product.objects.filter(pk=product.pk).update(sale_state=Product.SaleState.SOLD)

    product.refresh_from_db()
    assert product.sale_state == Product.SaleState.AVAILABLE
    assert ProductImage.objects.filter(pk=copied.pk).exists()


def test_old_app_cannot_replace_legacy_key_after_copy() -> None:
    """G7A-CAT-GUARD-002: old-app image UPDATE 뒤에도 source와 owned copy를 보존한다."""
    product, copied = _product_with_copy()
    original_legacy_key = product.image.name
    copied_key = copied.image.name

    with pytest.raises(
        DatabaseError, match="Product.image is frozen legacy media"
    ), transaction.atomic():
        Product.objects.filter(pk=product.pk).update(image="product-images/replaced.png")

    product.refresh_from_db()
    copied.refresh_from_db()
    assert product.image.name == original_legacy_key
    assert copied.image.name == copied_key
    assert copied.image.name != product.image.name


def test_old_app_cannot_delete_product_or_its_owned_copy() -> None:
    """G7A-CAT-GUARD-003: cutover 뒤 hard delete는 child cascade까지 원자적으로 되돌린다."""
    product, copied = _product_with_copy()

    with pytest.raises(
        DatabaseError,
        match="Product rows are archived, not deleted after catalog authority cutover",
    ), transaction.atomic():
        product.delete()

    assert Product.objects.filter(pk=product.pk).exists()
    assert ProductImage.objects.filter(pk=copied.pk).exists()


def test_product_image_database_guard_rejects_shared_legacy_storage_key() -> None:
    """G7A-CAT-GUARD-004: direct ORM, bulk, and SQL writes cannot alias legacy media."""
    product, copied = _product_with_copy()
    legacy_key = product.image.name
    copied_key = copied.image.name

    with pytest.raises(
        DatabaseError, match="catalog_product_image_legacy_key_alias"
    ), transaction.atomic():
        ProductImage.objects.create(
            product=product,
            image=legacy_key,
            position=1,
            sha256="0" * 64,
            byte_size=1,
            width=1,
            height=1,
        )
    assert not ProductImage.objects.filter(product=product, position=1).exists()

    copied.image = legacy_key
    with pytest.raises(
        DatabaseError, match="catalog_product_image_legacy_key_alias"
    ), transaction.atomic():
        copied.save(update_fields=("image",))
    copied.refresh_from_db()
    assert copied.image.name == copied_key

    with pytest.raises(
        DatabaseError, match="catalog_product_image_legacy_key_alias"
    ), transaction.atomic():
        ProductImage.objects.filter(pk=copied.pk).update(image=legacy_key)
    copied.refresh_from_db()
    assert copied.image.name == copied_key

    with pytest.raises(
        DatabaseError, match="catalog_product_image_legacy_key_alias"
    ), transaction.atomic():
        with connection.cursor() as cursor:
            cursor.execute(
                "UPDATE catalog_productimage SET image = %s WHERE id = %s",
                [legacy_key, copied.pk],
            )
    product.refresh_from_db()
    copied.refresh_from_db()
    assert product.image.name == legacy_key
    assert copied.image.name == copied_key


def test_database_guards_allow_unrelated_product_and_gallery_writes() -> None:
    """G7A-CAT-GUARD-005: authority triggers do not block ordinary owned writes."""
    product, copied = _product_with_copy()
    allowed_key = "product-images/owned/allowed.png"

    Product.objects.filter(pk=product.pk).update(title="수정 가능한 상품명")
    ProductImage.objects.filter(pk=copied.pk).update(image=allowed_key)

    product.refresh_from_db()
    copied.refresh_from_db()
    assert product.title == "수정 가능한 상품명"
    assert product.image.name == "product-images/legacy-source.png"
    assert copied.image.name == allowed_key