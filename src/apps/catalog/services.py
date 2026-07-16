from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol

from django.core.files.uploadedfile import UploadedFile

from apps.accounts.models import User

from .models import Product

if TYPE_CHECKING:
    from apps.moderation.services import EffectiveProductVisibility

OWNER_MUTABLE_FIELDS = frozenset({"title", "description", "image"})
OWNER_IMMUTABLE_FIELDS = frozenset({"id", "owner_id", "version", "created_at", "updated_at"})
ALLOWED_IMAGE_CONTENT_TYPES = frozenset({"image/jpeg", "image/png", "image/webp"})
MAX_IMAGE_BYTES = 5 * 1024 * 1024
MAX_IMAGE_DIMENSION = 4_096


@dataclass(frozen=True, slots=True)
class SanitizedProductImage:
    """Metadata returned only after full decode and safe re-encoding."""

    storage_name: str
    content_type: str
    width: int
    height: int
    byte_size: int


class ProductImagePipeline(Protocol):
    def sanitize(self, *, upload: UploadedFile) -> SanitizedProductImage: ...


class ProductVisibilityPolicy(Protocol):
    """Canonical DB-time visibility authority used by every product entrypoint."""

    def effective_visibility(self, *, product_id: int) -> EffectiveProductVisibility: ...


class ProductOwnershipPolicy(Protocol):
    """Owner authorization boundary; object IDs alone never grant access."""

    def may_manage(self, *, actor: User, product: Product) -> bool: ...
