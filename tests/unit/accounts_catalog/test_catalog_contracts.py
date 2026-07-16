import pytest
from django.db import IntegrityError, transaction
from django.db.models.deletion import ProtectedError

from apps.accounts.models import User
from apps.catalog.models import Product
from apps.catalog.services import (
    ALLOWED_IMAGE_CONTENT_TYPES,
    MAX_IMAGE_BYTES,
    MAX_IMAGE_DIMENSION,
    OWNER_IMMUTABLE_FIELDS,
    OWNER_MUTABLE_FIELDS,
    ProductImagePipeline,
)

pytestmark = pytest.mark.django_db


def test_product_owner_is_explicit_and_protected() -> None:
    """TEST-ID CAT-OWNER-001: a product has one durable owner and cannot orphan on delete."""
    owner = User.objects.create_user(username="owner_01", password="not-a-real-secret-123")
    product = Product.objects.create(
        owner=owner,
        title="Example",
        description="Description",
        price=10_000,
    )

    assert product.owner_id == owner.pk
    with pytest.raises(ProtectedError):
        owner.delete()


def test_product_owner_update_boundary_excludes_authority_fields() -> None:
    """TEST-ID CAT-OWNER-002: owner edits cannot rebind ownership or version authority."""
    assert OWNER_MUTABLE_FIELDS == {"title", "description", "price", "sale_state", "image"}
    assert {"id", "owner_id", "version", "created_at", "updated_at"} <= OWNER_IMMUTABLE_FIELDS
    assert OWNER_MUTABLE_FIELDS.isdisjoint(OWNER_IMMUTABLE_FIELDS)


def test_product_price_and_sale_state_have_database_constraints() -> None:
    owner = User.objects.create_user(username="owner_01", password="not-a-real-secret-123")

    with pytest.raises(IntegrityError), transaction.atomic():
        Product.objects.create(
            owner=owner,
            title="Invalid price",
            description="Description",
            price=0,
        )

    with pytest.raises(IntegrityError), transaction.atomic():
        Product.objects.create(
            owner=owner,
            title="Invalid state",
            description="Description",
            price=1,
            sale_state="INVALID",
        )


def test_product_has_no_persisted_visibility_shortcut() -> None:
    """TEST-ID POL-STATUS-002-CAT-001: visibility is derived by the canonical DB-time policy."""
    field_names = {field.name for field in Product._meta.get_fields()}

    assert "visibility" not in field_names
    assert "is_hidden" not in field_names


def test_product_image_pipeline_contract_has_security_boundaries() -> None:
    """TEST-ID CAT-IMAGE-001: ingestion requires bounded decode and safe re-encoding."""
    assert ALLOWED_IMAGE_CONTENT_TYPES == {"image/jpeg", "image/png", "image/webp"}
    assert MAX_IMAGE_BYTES == 5 * 1024 * 1024
    assert MAX_IMAGE_DIMENSION == 4_096
    assert hasattr(ProductImagePipeline, "sanitize")
