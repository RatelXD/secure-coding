from __future__ import annotations

from hashlib import sha256

import pytest
from django.core.files.base import ContentFile
from django.core.files.storage import FileSystemStorage
from django.db import transaction
from django.urls import reverse
from apps.accounts.models import User
from apps.catalog.models import Category, Product, ProductImage, ProductImageDeletionIntent
from apps.catalog.services import (
    SanitizedProductImage,
    _persist_exception_cleanup_failures,
    _record_cleanup_failures,
    repair_product_image_deletions,
    repair_product_image_promotions,
    replace_product_images,
)

pytestmark = pytest.mark.django_db(transaction=True)


def _storage(tmp_path, monkeypatch) -> FileSystemStorage:
    storage = FileSystemStorage(location=tmp_path, base_url="/media/")
    monkeypatch.setattr(ProductImage._meta.get_field("image"), "storage", storage)
    return storage


def _product(*, legacy_key: str = "") -> Product:
    category, _ = Category.objects.get_or_create(
        code="LIFECYCLE", defaults={"label": "Lifecycle", "display_order": 999}
    )
    owner = User.objects.create_user(username=f"lifecycle_{User.objects.count()}", password="long-password-123")
    return Product.objects.create(
        owner=owner,
        title="Lifecycle product",
        description="gallery lifecycle test",
        price=100,
        category=category,
        image=legacy_key,
    )


def _image(payload: bytes = b"gallery-bytes") -> SanitizedProductImage:
    return SanitizedProductImage(
        storage_name="upload.png",
        content_type="image/png",
        width=1,
        height=1,
        byte_size=len(payload),
        content=payload,
    )


def _gallery_row(
    *,
    product: Product,
    storage: FileSystemStorage,
    image_name: str,
    owned_key: str,
    payload: bytes,
    position: int,
    promotion_state: str,
) -> ProductImage:
    storage.save(image_name, ContentFile(payload))
    if owned_key != image_name:
        storage.save(owned_key, ContentFile(payload))
    return ProductImage.objects.create(
        product=product,
        image=image_name,
        owned_key=owned_key,
        position=position,
        sha256=sha256(payload).hexdigest(),
        byte_size=len(payload),
        width=1,
        height=1,
        promotion_state=promotion_state,
    )


def test_outer_rollback_cleanup_removes_all_staged_keys(tmp_path, monkeypatch) -> None:
    storage = _storage(tmp_path, monkeypatch)
    product = _product()
    staging = None

    with pytest.raises(RuntimeError, match="injected view failure"):
        try:
            with transaction.atomic():
                staging = replace_product_images(product=product, images=[_image(b"one"), _image(b"two")])
                raise RuntimeError("injected view failure")
        except Exception:
            if staging is not None:
                staging.cleanup()
            raise

    assert not [path for path in tmp_path.rglob("*") if path.is_file()]
    assert not ProductImage.objects.filter(product=product).exists()
    assert not product.image.name


def test_promotion_failure_is_durable_and_repairable(tmp_path, monkeypatch) -> None:
    storage = _storage(tmp_path, monkeypatch)
    product = _product()
    original_delete = storage.delete
    monkeypatch.setattr(storage, "delete", lambda name: (_ for _ in ()).throw(OSError("promotion delete failure")))

    with transaction.atomic():
        replace_product_images(product=product, images=[_image()])

    staged = ProductImage.objects.get(product=product)
    assert staged.promotion_state == "PENDING"
    assert staged.image.name.startswith("product-images/tmp/")
    assert storage.exists(staged.owned_key)

    monkeypatch.setattr(storage, "delete", original_delete)
    repair_product_image_promotions()
    staged.refresh_from_db()
    assert staged.promotion_state == "PROMOTED"
    assert staged.image.name == staged.owned_key
    repair_product_image_promotions()


def test_failed_superseded_delete_remains_in_outbox_until_repaired(tmp_path, monkeypatch) -> None:
    storage = _storage(tmp_path, monkeypatch)
    product = _product()
    with transaction.atomic():
        replace_product_images(product=product, images=[_image(b"old")])
    old = ProductImage.objects.get(product=product)
    original_delete = storage.delete
    monkeypatch.setattr(storage, "delete", lambda name: (_ for _ in ()).throw(OSError("delete failure")))
    with transaction.atomic():
        replace_product_images(product=product, images=[])

    intent = ProductImageDeletionIntent.objects.get(storage_key=old.image.name)
    assert intent.attempts == 1
    with pytest.raises(OSError, match="delete failure"):
        repair_product_image_deletions()
    intent.refresh_from_db()
    assert intent.attempts == 2

    monkeypatch.setattr(storage, "delete", original_delete)
    repair_product_image_deletions()
    assert not ProductImageDeletionIntent.objects.filter(pk=intent.pk).exists()
    assert not storage.exists(old.image.name)
    repair_product_image_deletions()


def test_clear_gallery_creates_deletion_intent_without_touching_legacy_key(tmp_path, monkeypatch) -> None:
    storage = _storage(tmp_path, monkeypatch)
    legacy_key = "product-images/legacy/product.png"
    storage.save(legacy_key, ContentFile(_image(b"legacy").content))
    product = _product(legacy_key=legacy_key)

    with transaction.atomic():
        replace_product_images(product=product, images=[_image(b"owned")])
    owned = ProductImage.objects.get(product=product)
    with transaction.atomic():
        replace_product_images(product=product, images=[])

    product.refresh_from_db()
    assert product.image.name == legacy_key
    assert storage.exists(legacy_key)
    assert not storage.exists(owned.image.name)
    assert not ProductImage.objects.filter(product=product).exists()


def test_mismatched_existing_owned_key_is_not_overwritten(tmp_path, monkeypatch) -> None:
    storage = _storage(tmp_path, monkeypatch)
    product = _product()
    with transaction.atomic():
        replace_product_images(product=product, images=[_image(b"expected")])
    image = ProductImage.objects.get(product=product)

    # Recreate a pending row with an occupied final key containing different bytes.
    storage.delete(image.owned_key)
    storage.save(image.owned_key, ContentFile(_image(b"different").content))
    image.image.name = "product-images/tmp/retry.png"
    storage.save(image.image.name, ContentFile(_image(b"expected").content))
    image.sha256 = sha256(b"expected").hexdigest()
    image.promotion_state = "PENDING"
    image.save(update_fields=("image", "sha256", "promotion_state"))

    with pytest.raises(RuntimeError, match="mismatched bytes"):
        repair_product_image_promotions()
    image.refresh_from_db()
    assert image.promotion_state == "PENDING"
    with storage.open(image.owned_key, "rb") as occupied:
        assert occupied.read() == b"different"


def test_pending_supersession_enqueues_temp_and_owned_keys(tmp_path, monkeypatch) -> None:
    storage = _storage(tmp_path, monkeypatch)
    product = _product()
    pending = _gallery_row(
        product=product,
        storage=storage,
        image_name="product-images/tmp/pending.png",
        owned_key="product-images/owned/pending.png",
        payload=b"pending",
        position=0,
        promotion_state="PENDING",
    )
    monkeypatch.setattr(
        storage,
        "delete",
        lambda name: (_ for _ in ()).throw(OSError(f"cannot delete {name}")),
    )

    with transaction.atomic():
        replace_product_images(product=product, images=[])

    assert set(
        ProductImageDeletionIntent.objects.values_list("storage_key", flat=True)
    ) == {pending.image.name, pending.owned_key}


def test_rollback_cleanup_failure_preserves_primary_exception_and_records_all_keys(
    tmp_path, monkeypatch
) -> None:
    storage = _storage(tmp_path, monkeypatch)
    product = _product()
    staging = None
    deleted_keys: list[str] = []

    def fail_delete(name: str) -> None:
        deleted_keys.append(name)
        raise OSError("cleanup failure")

    monkeypatch.setattr(storage, "delete", fail_delete)

    with pytest.raises(RuntimeError, match="injected view failure") as raised:
        try:
            with transaction.atomic():
                staging = replace_product_images(
                    product=product,
                    images=[_image(b"one"), _image(b"two")],
                )
                raise RuntimeError("injected view failure")
        except Exception as exc:
            if staging is not None:
                _record_cleanup_failures(exc=exc, keys=staging.cleanup())
            _persist_exception_cleanup_failures(exc=exc)
            raise

    assert isinstance(raised.value, RuntimeError)
    assert len(deleted_keys) == 2
    assert set(
        ProductImageDeletionIntent.objects.values_list("storage_key", flat=True)
    ) == {name for _, name in staging.files}

def test_cleanup_intent_persistence_failure_is_attached_and_logged(
    monkeypatch, caplog
) -> None:
    original = RuntimeError("primary transaction failure")
    _record_cleanup_failures(
        exc=original,
        keys=["product-images/owned/unrecorded.png"],
    )

    def fail_bulk_create(*args, **kwargs) -> None:
        raise OSError("intent database unavailable")

    monkeypatch.setattr(
        ProductImageDeletionIntent.objects,
        "bulk_create",
        fail_bulk_create,
    )

    with caplog.at_level("ERROR", logger="apps.catalog.services"):
        _persist_exception_cleanup_failures(exc=original)

    persistence_error = getattr(
        original,
        "_gallery_cleanup_persistence_error",
        None,
    )
    assert isinstance(persistence_error, OSError)
    assert "intent database unavailable" in str(persistence_error)
    assert "Failed to persist product image cleanup intents" in caplog.text


def test_renamed_owned_key_cleanup_failure_has_durable_intent(tmp_path, monkeypatch) -> None:
    storage = _storage(tmp_path, monkeypatch)
    product = _product()
    pending = _gallery_row(
        product=product,
        storage=storage,
        image_name="product-images/tmp/renamed.png",
        owned_key="product-images/owned/renamed.png",
        payload=b"pending",
        position=0,
        promotion_state="PENDING",
    )
    storage.delete(pending.owned_key)
    original_save = storage.save
    unexpected_key = f"{pending.owned_key}.unexpected"

    def rename_owned_key(name: str, content, max_length=None) -> str:
        if name == pending.owned_key:
            return original_save(unexpected_key, content, max_length=max_length)
        return original_save(name, content, max_length=max_length)

    def fail_unexpected_delete(name: str) -> None:
        if name == unexpected_key:
            raise OSError("unexpected cleanup failure")
        return FileSystemStorage.delete(storage, name)

    monkeypatch.setattr(storage, "save", rename_owned_key)
    monkeypatch.setattr(storage, "delete", fail_unexpected_delete)

    with pytest.raises(RuntimeError, match="changed the owned key"):
        repair_product_image_promotions()

    pending.refresh_from_db()
    assert pending.promotion_state == "PENDING"
    assert ProductImageDeletionIntent.objects.filter(storage_key=unexpected_key).exists()


def test_legacy_product_key_under_owned_prefix_is_never_superseded(tmp_path, monkeypatch) -> None:
    storage = _storage(tmp_path, monkeypatch)
    legacy_key = "product-images/owned/legacy-product.png"
    storage.save(legacy_key, ContentFile(b"legacy"))
    product = _product(legacy_key=legacy_key)
    _gallery_row(
        product=product,
        storage=storage,
        image_name="product-images/owned/service.png",
        owned_key="product-images/owned/service.png",
        payload=b"service",
        position=0,
        promotion_state="PROMOTED",
    )
    monkeypatch.setattr(
        storage,
        "delete",
        lambda name: (_ for _ in ()).throw(OSError(f"cannot delete {name}")),
    )

    with transaction.atomic():
        replace_product_images(product=product, images=[])

    assert storage.exists(legacy_key)
    assert not ProductImageDeletionIntent.objects.filter(storage_key=legacy_key).exists()


def test_public_views_exclude_pending_gallery_rows(tmp_path, monkeypatch, client) -> None:
    storage = _storage(tmp_path, monkeypatch)
    product = _product()
    promoted = _gallery_row(
        product=product,
        storage=storage,
        image_name="product-images/owned/public.png",
        owned_key="product-images/owned/public.png",
        payload=b"public",
        position=0,
        promotion_state="PROMOTED",
    )
    pending = _gallery_row(
        product=product,
        storage=storage,
        image_name="product-images/tmp/private.png",
        owned_key="product-images/owned/private.png",
        payload=b"private",
        position=1,
        promotion_state="PENDING",
    )

    detail = client.get(reverse("catalog:detail", args=[product.pk]))
    listing = client.get(reverse("catalog:list"))

    assert promoted.image.url.encode() in detail.content
    assert pending.image.url.encode() not in detail.content
    assert promoted.image.url.encode() in listing.content
    assert pending.image.url.encode() not in listing.content
