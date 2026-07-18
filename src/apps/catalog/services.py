from __future__ import annotations

import logging
from dataclasses import dataclass
from hashlib import sha256
from io import BytesIO
from pathlib import PurePosixPath
from typing import TYPE_CHECKING, Iterable, Protocol
from uuid import uuid4

from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from django.core.files.uploadedfile import UploadedFile
from django.db import transaction
from PIL import Image, UnidentifiedImageError

from apps.accounts.models import User

from .models import Product, ProductImage, ProductImageDeletionIntent

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from apps.moderation.services import EffectiveProductVisibility

OWNER_MUTABLE_FIELDS = frozenset(
    {"title", "description", "price", "category_id", "region_id", "region_source"}
)
OWNER_IMMUTABLE_FIELDS = frozenset(
    {
        "id",
        "owner_id",
        "sale_state",
        "image",
        "version",
        "created_at",
        "updated_at",
    }
)
ALLOWED_IMAGE_CONTENT_TYPES = frozenset({"image/jpeg", "image/png", "image/webp"})
MAX_IMAGE_BYTES = 5 * 1024 * 1024
MAX_IMAGE_DIMENSION = 4_096

_IMAGE_FORMATS = {
    "JPEG": ("image/jpeg", "jpg"),
    "PNG": ("image/png", "png"),
    "WEBP": ("image/webp", "webp"),
}
_INVALID_IMAGE_MESSAGE = "JPEG, PNG 또는 WebP 형식의 안전한 이미지 파일을 선택해 주세요."


@dataclass(frozen=True, slots=True)
class SanitizedProductImage:
    """A newly encoded image and its storage-safe metadata."""

    storage_name: str
    content_type: str
    width: int
    height: int
    byte_size: int
    content: bytes


class ProductImagePipeline(Protocol):
    def sanitize(self, *, upload: UploadedFile) -> SanitizedProductImage: ...


class PillowProductImagePipeline:
    """Bounded, full-decode image ingestion with metadata-free re-encoding."""

    def sanitize(self, *, upload: UploadedFile) -> SanitizedProductImage:
        self._validate_name(upload.name)
        declared_type = (upload.content_type or "").lower()
        if declared_type not in ALLOWED_IMAGE_CONTENT_TYPES:
            raise ValidationError(_INVALID_IMAGE_MESSAGE)

        raw = self._read_bounded(upload)
        self._validate_container(raw)

        try:
            with Image.open(BytesIO(raw)) as probe:
                image_format = (probe.format or "").upper()
                if image_format not in _IMAGE_FORMATS:
                    raise ValidationError(_INVALID_IMAGE_MESSAGE)
                actual_type, extension = _IMAGE_FORMATS[image_format]
                if declared_type != actual_type:
                    raise ValidationError(_INVALID_IMAGE_MESSAGE)
                if getattr(probe, "n_frames", 1) != 1:
                    raise ValidationError(_INVALID_IMAGE_MESSAGE)
                width, height = probe.size
                self._validate_dimensions(width, height)
                probe.verify()

            with Image.open(BytesIO(raw)) as decoded:
                decoded.load()
                self._validate_dimensions(*decoded.size)
                encoded = self._encode(decoded, image_format)
                if len(encoded) > MAX_IMAGE_BYTES:
                    raise ValidationError("재인코딩한 이미지가 5 MiB 제한을 초과합니다.")
        except ValidationError:
            raise
        except (Image.DecompressionBombError, UnidentifiedImageError, OSError, SyntaxError, ValueError) as exc:
            raise ValidationError(_INVALID_IMAGE_MESSAGE) from exc

        return SanitizedProductImage(
            storage_name=f"{uuid4()}.{extension}",
            content_type=actual_type,
            width=width,
            height=height,
            byte_size=len(encoded),
            content=encoded,
        )

    @staticmethod
    def _validate_name(name: str) -> None:
        if (
            not name
            or "\x00" in name
            or "\\" in name
            or "/" in name
            or PurePosixPath(name).name != name
            or name in {".", ".."}
        ):
            raise ValidationError(_INVALID_IMAGE_MESSAGE)

    @staticmethod
    def _read_bounded(upload: UploadedFile) -> bytes:
        upload.seek(0)
        chunks: list[bytes] = []
        byte_count = 0
        for chunk in upload.chunks():
            byte_count += len(chunk)
            if byte_count > MAX_IMAGE_BYTES:
                raise ValidationError("이미지 파일은 5 MiB 이하여야 합니다.")
            chunks.append(chunk)
        if byte_count == 0:
            raise ValidationError(_INVALID_IMAGE_MESSAGE)
        return b"".join(chunks)

    @staticmethod
    def _validate_container(raw: bytes) -> None:
        is_jpeg = raw.startswith(b"\xff\xd8") and raw.endswith(b"\xff\xd9")
        is_png = raw.startswith(b"\x89PNG\r\n\x1a\n") and raw.endswith(
            b"\x00\x00\x00\x00IEND\xaeB`\x82"
        )
        is_webp = (
            len(raw) >= 12
            and raw.startswith(b"RIFF")
            and raw[8:12] == b"WEBP"
            and int.from_bytes(raw[4:8], "little") + 8 == len(raw)
        )
        if not (is_jpeg or is_png or is_webp):
            raise ValidationError(_INVALID_IMAGE_MESSAGE)

    @staticmethod
    def _validate_dimensions(width: int, height: int) -> None:
        if not 0 < width <= MAX_IMAGE_DIMENSION or not 0 < height <= MAX_IMAGE_DIMENSION:
            raise ValidationError("이미지 크기는 4096×4096 이하여야 합니다.")

    @staticmethod
    def _encode(image: Image.Image, image_format: str) -> bytes:
        output = BytesIO()
        if image_format == "JPEG":
            image.convert("RGB").save(output, format="JPEG", quality=90, optimize=True)
        elif image_format == "PNG":
            mode = "RGBA" if "A" in image.getbands() else "RGB"
            image.convert(mode).save(output, format="PNG", optimize=True)
        else:
            mode = "RGBA" if "A" in image.getbands() else "RGB"
            image.convert(mode).save(output, format="WEBP", lossless=True, method=6)
        return output.getvalue()


product_image_pipeline = PillowProductImagePipeline()


@dataclass(slots=True)
class GalleryStaging:
    """Temp storage keys that must be removed if the owning transaction rolls back."""

    files: list[tuple[object, str]]

    def cleanup(self) -> list[str]:
        failed_keys: list[str] = []
        for storage, name in self.files:
            try:
                storage.delete(name)
            except Exception:
                failed_keys.append(name)
        return failed_keys

def _record_cleanup_failures(*, exc: Exception, keys: Iterable[str]) -> None:
    failed_keys = list(getattr(exc, "_gallery_cleanup_failed_keys", ()))
    failed_keys.extend(keys)
    exc._gallery_cleanup_failed_keys = tuple(dict.fromkeys(failed_keys))


def _persist_deletion_intents(*, keys: Iterable[str]) -> None:
    unique_keys = tuple(dict.fromkeys(key for key in keys if key))
    if unique_keys:
        ProductImageDeletionIntent.objects.bulk_create(
            [ProductImageDeletionIntent(storage_key=key) for key in unique_keys],
            ignore_conflicts=True,
        )


def _persist_exception_cleanup_failures(*, exc: Exception) -> None:
    keys = tuple(getattr(exc, "_gallery_cleanup_failed_keys", ()))
    try:
        _persist_deletion_intents(keys=keys)
    except Exception as persistence_error:
        exc._gallery_cleanup_persistence_error = persistence_error
        logger.exception(
            "Failed to persist product image cleanup intents",
            extra={"cleanup_keys": keys},
        )



def replace_product_images(
    *,
    product: Product,
    images: list[SanitizedProductImage],
) -> GalleryStaging:
    """Stage a gallery replacement inside the caller's explicit outer transaction."""
    if not transaction.get_connection().in_atomic_block:
        raise RuntimeError("replace_product_images requires an outer transaction")
    if len(images) > 4:
        raise ValidationError("상품 이미지는 최대 4장까지 등록할 수 있습니다.")

    staging = GalleryStaging(files=[])
    try:
        locked_product = Product.objects.select_for_update().get(pk=product.pk)
        existing_images = list(
            ProductImage.objects.select_for_update()
            .filter(product=locked_product)
            .only("id", "image", "promotion_state", "owned_key")
        )
        protected_names = {
            name
            for name in (
                locked_product.image.name,
                *(image.image.name for image in existing_images),
                *(image.owned_key for image in existing_images),
            )
            if name
        }
        new_images: list[ProductImage] = []

        for position, sanitized in enumerate(images):
            extension = PurePosixPath(sanitized.storage_name).suffix.lower()
            temp_name = f"product-images/tmp/{uuid4()}{extension}"
            owned_name = f"product-images/owned/{locked_product.pk}/{uuid4()}{extension}"
            if temp_name in protected_names or owned_name in protected_names:
                raise RuntimeError("gallery image destination aliases an existing image key")

            storage = ProductImage._meta.get_field("image").storage
            saved_name = storage.save(temp_name, ContentFile(sanitized.content))
            staging.files.append((storage, saved_name))
            if saved_name != temp_name:
                raise RuntimeError("gallery image storage changed the temporary key")

            new_images.append(
                ProductImage(
                    product=locked_product,
                    image=saved_name,
                    position=position,
                    sha256=sha256(sanitized.content).hexdigest(),
                    byte_size=sanitized.byte_size,
                    width=sanitized.width,
                    height=sanitized.height,
                    owned_key=owned_name,
                    promotion_state="PENDING",
                )
            )
            protected_names.update({saved_name, owned_name})

        superseded_keys = {
            image.image.name
            for image in existing_images
            if image.promotion_state == "PROMOTED"
        }
        superseded_keys.update(
            key
            for image in existing_images
            if image.promotion_state == "PENDING"
            for key in (image.image.name, image.owned_key)
        )
        superseded_keys.discard(locked_product.image.name)
        _persist_deletion_intents(keys=superseded_keys)
        ProductImage.objects.filter(product=locked_product).delete()
        ProductImage.objects.bulk_create(new_images)
        transaction.on_commit(
            lambda: _repair_after_commit(product_id=locked_product.pk)
        )
    except Exception as exc:
        _record_cleanup_failures(exc=exc, keys=staging.cleanup())
        raise
    return staging


def _repair_after_commit(*, product_id: int) -> None:
    try:
        promote_product_images(product_id=product_id)
    except Exception:
        # The pending row and staged bytes are the durable retry record.
        pass
    try:
        repair_product_image_deletions()
    except Exception:
        # The deletion intent remains durable until a later repair succeeds.
        pass

def _storage_checksum(*, storage, name: str) -> str:
    with storage.open(name, "rb") as stored:
        return sha256(stored.read()).hexdigest()


def promote_product_images(
    *,
    image_ids: Iterable[int] | None = None,
    product_id: int | None = None,
) -> None:
    """Promote staged keys without overwriting bytes at an occupied owned key."""
    queryset = ProductImage.objects.filter(promotion_state="PENDING")
    if image_ids is not None:
        queryset = queryset.filter(pk__in=image_ids)
    if product_id is not None:
        queryset = queryset.filter(product_id=product_id)
    failures: list[Exception] = []
    for image_id in queryset.values_list("pk", flat=True):
        try:
            with transaction.atomic():
                image = ProductImage.objects.select_for_update().get(pk=image_id)
                if image.promotion_state != "PENDING":
                    continue
                storage = image.image.storage
                final_name = image.owned_key
                if storage.exists(final_name):
                    if _storage_checksum(storage=storage, name=final_name) != image.sha256:
                        raise RuntimeError("gallery image owned key has mismatched bytes")
                else:
                    with storage.open(image.image.name, "rb") as staged:
                        saved_name = storage.save(final_name, ContentFile(staged.read()))
                    if saved_name != final_name:
                        cleanup_error: Exception | None = None
                        try:
                            storage.delete(saved_name)
                        except Exception as exc:
                            cleanup_error = exc
                        error = RuntimeError("gallery image storage changed the owned key")
                        if cleanup_error is not None:
                            _record_cleanup_failures(exc=error, keys=(saved_name,))
                        raise error
                    if _storage_checksum(storage=storage, name=final_name) != image.sha256:
                        raise RuntimeError("gallery image owned key checksum mismatch")

                storage.delete(image.image.name)
                image.image.name = final_name
                image.promotion_state = "PROMOTED"
                image.save(update_fields=("image", "promotion_state"))
        except Exception as exc:
            _persist_exception_cleanup_failures(exc=exc)
            failures.append(exc)
    if failures:
        raise failures[0]


def repair_product_image_promotions() -> None:
    """Idempotently retry every persisted staged-image promotion."""
    promote_product_images()


def repair_product_image_deletions() -> None:
    """Idempotently retry every durable owned-key deletion intent."""
    storage = ProductImage._meta.get_field("image").storage
    failures: list[Exception] = []
    for intent_id in ProductImageDeletionIntent.objects.values_list("pk", flat=True):
        try:
            with transaction.atomic():
                intent = ProductImageDeletionIntent.objects.select_for_update().get(pk=intent_id)
                intent.record_attempt()
            storage.delete(intent.storage_key)
            with transaction.atomic():
                ProductImageDeletionIntent.objects.filter(pk=intent_id).delete()
        except Exception as exc:
            failures.append(exc)
    if failures:
        raise failures[0]


def repair_product_image_lifecycle() -> None:
    """Repair both independently retryable gallery lifecycle phases."""
    repair_product_image_promotions()
    repair_product_image_deletions()


def is_product_public(*, product_id: int) -> bool:
    """Consult the canonical DB-time moderation authority for public exposure."""
    from apps.moderation.services import EffectiveProductVisibility, effective_product_visibility

    return (
        effective_product_visibility(product_id=product_id)
        == EffectiveProductVisibility.VISIBLE
    )


class ProductVisibilityPolicy(Protocol):
    """Canonical DB-time visibility authority used by every product entrypoint."""

    def effective_visibility(self, *, product_id: int) -> EffectiveProductVisibility: ...


class ProductOwnershipPolicy(Protocol):
    """Owner authorization boundary; object IDs alone never grant access."""

    def may_manage(self, *, actor: User, product: Product) -> bool: ...
