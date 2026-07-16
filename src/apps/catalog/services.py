from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
from pathlib import PurePosixPath
from typing import TYPE_CHECKING, Protocol
from uuid import uuid4

from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import UploadedFile
from PIL import Image, UnidentifiedImageError

from apps.accounts.models import User

from .models import Product

if TYPE_CHECKING:
    from apps.moderation.services import EffectiveProductVisibility

OWNER_MUTABLE_FIELDS = frozenset({"title", "description", "price", "sale_state", "image"})
OWNER_IMMUTABLE_FIELDS = frozenset({"id", "owner_id", "version", "created_at", "updated_at"})
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
