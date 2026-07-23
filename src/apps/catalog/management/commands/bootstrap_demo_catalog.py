from __future__ import annotations

import hashlib
import json
import os
import re
from dataclasses import dataclass
from io import BytesIO
from importlib.resources import files
from pathlib import PurePosixPath
from uuid import uuid4

from django.conf import settings
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.core.management.base import BaseCommand, CommandError
from django.db import connection, transaction
from PIL import Image, UnidentifiedImageError

from apps.accounts.models import User
from apps.catalog.models import Category, Product, ProductImage, ProductMetric, Region


_DEMO_IMAGE_NAME = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*-[1-4]\.png\Z")
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_MAX_IMAGE_BYTES = 5 * 1024 * 1024
_MAX_IMAGE_DIMENSION = 4_096
_DEMO_IMAGE_COUNT = 50


@dataclass(frozen=True, slots=True)
class VerifiedDemoImage:
    """Manifest-validated PNG bytes and their decoded dimensions."""

    content: bytes
    width: int
    height: int


class Command(BaseCommand):
    help = "개발 환경에 checksum으로 고정된 17개 로컬 데모 상품을 멱등 설치합니다."

    def handle(self, *args, **options):
        if settings.APP_ENV != "development" or not settings.DEMO_CATALOG_BOOTSTRAP_ENABLED:
            raise CommandError("데모 카탈로그 bootstrap은 명시적으로 허용된 개발 환경에서만 실행됩니다.")
        manifest, root = _load_manifest()
        products = manifest.get("products")
        if not isinstance(products, list) or len(products) != 17:
            raise CommandError("데모 manifest는 정확히 17개 상품이어야 합니다.")
        if not all(isinstance(item, dict) for item in products):
            raise CommandError("데모 manifest 상품 형식이 안전하지 않습니다.")
        keys = [item.get("key") for item in products]
        if any(not isinstance(key, str) or not key for key in keys) or len(set(keys)) != 17:
            raise CommandError("데모 상품 key는 17개 모두 고유해야 합니다.")
        if any(
            not isinstance(item.get("images"), list) or not 2 <= len(item["images"]) <= 4
            for item in products
        ):
            raise CommandError("각 데모 상품은 2~4개 로컬 이미지를 가져야 합니다.")
        if sum(len(item["images"]) for item in products) != _DEMO_IMAGE_COUNT:
            raise CommandError(f"데모 manifest는 정확히 {_DEMO_IMAGE_COUNT}개 이미지를 가져야 합니다.")

        assets = _verify_sources(products=products, root=root)
        with transaction.atomic():
            if connection.vendor == "postgresql":
                with connection.cursor() as cursor:
                    cursor.execute("SELECT pg_advisory_xact_lock(%s)", [0x434154414C4F47])
            owner, created = User.objects.select_for_update().get_or_create(
                username="demo_catalog_owner",
                defaults={"is_active": True, "first_name": "데모 판매자"},
            )
            if not created and owner.has_usable_password():
                raise CommandError("예약된 데모 owner 계정이 일반 계정과 충돌합니다.")
            owner.is_active = True
            owner.first_name = "데모 판매자"
            owner.set_unusable_password()
            owner.save(update_fields=("is_active", "first_name", "password"))

            for item in products:
                category = Category.objects.get(pk=item["category"])
                region = Region.objects.get(pk=item["region"])
                product, _ = Product.objects.select_for_update().update_or_create(
                    demo_key=item["key"],
                    defaults={
                        "owner": owner,
                        "title": item["title"],
                        "description": item["description"],
                        "price": item["price"],
                        "category": category,
                        "region": region,
                        "region_source": Product.RegionSource.SELECTED,
                        "archived_at": None,
                    },
                )
                expected_keys = []
                for position, image in enumerate(item["images"]):
                    final_key = f"product-images/demo/{item['key']}/{image['file']}"
                    asset = assets[image["file"]]
                    _install_asset(final_key=final_key, content=asset.content, checksum=image["sha256"])
                    expected_keys.append(final_key)
                    ProductImage.objects.update_or_create(
                        product=product,
                        position=position,
                        defaults={
                            "image": final_key,
                            "sha256": image["sha256"],
                            "byte_size": len(asset.content),
                            "width": asset.width,
                            "height": asset.height,
                            "owned_key": final_key,
                            "promotion_state": "PROMOTED",
                        },
                    )
                ProductImage.objects.filter(product=product).exclude(image__in=expected_keys).delete()
                ProductMetric.objects.get_or_create(product=product)

            if Product.objects.filter(owner=owner, demo_key__isnull=True).exists():
                raise CommandError("고정 데모 owner에 manifest 밖 상품이 있어 bootstrap을 중단합니다.")
            if Product.objects.filter(owner=owner).count() != 17:
                raise CommandError("데모 상품 수가 정확히 17개가 아닙니다.")
        self.stdout.write(self.style.SUCCESS("데모 상품 17개와 로컬 이미지를 검증·복구했습니다."))


def _load_manifest():
    root = files("apps.catalog.data.demo")
    manifest = json.loads(root.joinpath("manifest.json").read_text(encoding="utf-8"))
    generator = manifest.get("generator", {})
    if generator.get("name") != "agy" or generator.get("version") != "1.1.4" or generator.get("mode") != "sequential":
        raise CommandError("데모 생성기 manifest가 승인 계약과 다릅니다.")
    return manifest, root


def _verify_sources(*, products, root) -> dict[str, VerifiedDemoImage]:
    assets: dict[str, VerifiedDemoImage] = {}
    for item in products:
        images = item.get("images")
        if not isinstance(images, list) or not 2 <= len(images) <= 4:
            raise CommandError("각 데모 상품은 2~4개 로컬 이미지를 가져야 합니다.")
        for image in images:
            if not isinstance(image, dict):
                raise CommandError("데모 이미지 형식이 안전하지 않습니다.")
            name = image.get("file", "")
            checksum = image.get("sha256")
            content_type = image.get("content_type")
            byte_size = image.get("byte_size")
            width = image.get("width")
            height = image.get("height")
            if (
                not isinstance(name, str)
                or not _DEMO_IMAGE_NAME.fullmatch(name)
                or PurePosixPath(name).name != name
                or name in assets
            ):
                raise CommandError("데모 이미지 이름이 안전하지 않거나 중복됩니다.")
            if not isinstance(checksum, str) or not _SHA256.fullmatch(checksum):
                raise CommandError(f"데모 이미지 checksum 형식이 안전하지 않습니다: {name}")
            if content_type != "image/png":
                raise CommandError(f"데모 이미지 MIME type이 PNG가 아닙니다: {name}")
            if (
                not isinstance(byte_size, int)
                or isinstance(byte_size, bool)
                or not 0 < byte_size <= _MAX_IMAGE_BYTES
                or not isinstance(width, int)
                or isinstance(width, bool)
                or not 0 < width <= _MAX_IMAGE_DIMENSION
                or not isinstance(height, int)
                or isinstance(height, bool)
                or not 0 < height <= _MAX_IMAGE_DIMENSION
            ):
                raise CommandError(f"데모 이미지 크기 metadata가 안전하지 않습니다: {name}")
            try:
                content = root.joinpath(name).read_bytes()
            except (FileNotFoundError, OSError) as exc:
                raise CommandError(f"데모 이미지 원본을 읽을 수 없습니다: {name}") from exc
            if len(content) != byte_size:
                raise CommandError(f"데모 이미지 byte size 불일치: {name}")
            if hashlib.sha256(content).hexdigest() != checksum:
                raise CommandError(f"데모 원본 checksum 불일치: {name}")
            try:
                with Image.open(BytesIO(content)) as probe:
                    actual_width, actual_height = probe.size
                    if probe.format != "PNG" or probe.n_frames != 1:
                        raise CommandError(f"데모 이미지 형식이 PNG 단일 프레임이 아닙니다: {name}")
                    if (actual_width, actual_height) != (width, height):
                        raise CommandError(f"데모 이미지 dimensions 불일치: {name}")
                    probe.verify()
                with Image.open(BytesIO(content)) as decoded:
                    decoded.load()
                    if decoded.format != "PNG" or decoded.size != (width, height):
                        raise CommandError(f"데모 이미지 decode 결과가 metadata와 다릅니다: {name}")
            except CommandError:
                raise
            except (Image.DecompressionBombError, UnidentifiedImageError, OSError, SyntaxError, ValueError) as exc:
                raise CommandError(f"데모 이미지 decode에 실패했습니다: {name}") from exc
            assets[name] = VerifiedDemoImage(content=content, width=width, height=height)
    return assets


def _install_asset(*, final_key: str, content: bytes, checksum: str) -> None:
    if default_storage.exists(final_key):
        with default_storage.open(final_key, "rb") as installed:
            if hashlib.sha256(installed.read()).hexdigest() != checksum:
                raise CommandError(f"기존 데모 이미지 checksum 충돌: {final_key}")
        return
    try:
        final_path = default_storage.path(final_key)
    except NotImplementedError:
        saved = default_storage.save(final_key, ContentFile(content))
        if saved != final_key:
            default_storage.delete(saved)
            raise CommandError("storage가 고정 데모 key를 변경했습니다.")
        return
    os.makedirs(os.path.dirname(final_path), exist_ok=True)
    temp_path = f"{final_path}.tmp-{uuid4()}"
    try:
        with open(temp_path, "xb") as target:
            target.write(content)
            target.flush()
            os.fsync(target.fileno())
        if os.path.exists(final_path):
            with open(final_path, "rb") as installed:
                if hashlib.sha256(installed.read()).hexdigest() != checksum:
                    raise CommandError(f"기존 데모 이미지 checksum 충돌: {final_key}")
        else:
            os.replace(temp_path, final_path)
    finally:
        if os.path.exists(temp_path):
            os.unlink(temp_path)
