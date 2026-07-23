from io import BytesIO
from hashlib import sha256
import json
from importlib.resources import files
from uuid import UUID

import pytest
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management.base import CommandError
from PIL import Image, PngImagePlugin

from apps.catalog.management.commands.bootstrap_demo_catalog import _verify_sources
from apps.catalog.services import MAX_IMAGE_BYTES, PillowProductImagePipeline


def test_demo_manifest_characterizes_stable_product_keys() -> None:
    """Given the committed demo manifest, its product identifiers remain stable."""
    manifest = json.loads(
        files("apps.catalog.data.demo").joinpath("manifest.json").read_text(encoding="utf-8")
    )

    assert [product["key"] for product in manifest["products"]] == [
        "compact-laptop",
        "wireless-speaker",
        "coffee-grinder",
        "cast-iron-pan",
        "oak-side-table",
        "reading-lamp",
        "linen-jacket",
        "leather-backpack",
        "camping-chair",
        "yoga-mat",
        "classic-novel-set",
        "coding-book",
        "plant-pot",
        "tool-box",
        "mechanical-keyboard",
        "wool-blanket",
        "road-bicycle",
    ]


def test_demo_manifest_has_verified_ordered_gallery_assets() -> None:
    """Given the demo fixture, every product has the selected ordered PNG gallery."""
    root = files("apps.catalog.data.demo")
    manifest = json.loads(root.joinpath("manifest.json").read_text(encoding="utf-8"))
    selected_positions = {
        "compact-laptop": (1, 2, 3, 4),
        "wireless-speaker": (1, 2, 4),
        "coffee-grinder": (2, 3),
        "cast-iron-pan": (1, 2, 3, 4),
        "oak-side-table": (1, 3, 4),
        "reading-lamp": (2, 4),
        "linen-jacket": (1, 2, 4),
        "leather-backpack": (1, 2, 3, 4),
        "camping-chair": (1, 3),
        "yoga-mat": (2, 3, 4),
        "classic-novel-set": (1, 4),
        "coding-book": (1, 2, 3, 4),
        "plant-pot": (1, 2, 3),
        "tool-box": (2, 4),
        "mechanical-keyboard": (1, 2, 3, 4),
        "wool-blanket": (1, 3, 4),
        "road-bicycle": (1, 2),
    }

    assert len(manifest["products"]) == 17
    assert [product["key"] for product in manifest["products"]] == list(selected_positions)
    for product in manifest["products"]:
        images = product["images"]
        assert 2 <= len(images) <= 4
        assert [image["file"] for image in images] == [
            f"{product['key']}-{position}.png" for position in selected_positions[product["key"]]
        ]
        for image in images:
            content = root.joinpath(image["file"]).read_bytes()
            assert sha256(content).hexdigest() == image["sha256"]
            assert len(content) == image["byte_size"]
            assert image["content_type"] == "image/png"
            with Image.open(BytesIO(content)) as decoded:
                decoded.load()
                assert decoded.format == "PNG"
                assert decoded.size == (image["width"], image["height"])


def image_bytes(image_format: str = "PNG", *, size: tuple[int, int] = (8, 8)) -> bytes:
    output = BytesIO()
    image = Image.new("RGBA", size, (10, 20, 30, 255))
    if image_format == "JPEG":
        image = image.convert("RGB")
    image.save(output, format=image_format)
    return output.getvalue()


def verified_demo_images(tmp_path) -> list[dict[str, int | str]]:
    """Create two valid fixture PNG entries that a metadata mutation can invalidate."""
    content = image_bytes()
    metadata = {
        "sha256": sha256(content).hexdigest(),
        "byte_size": len(content),
        "content_type": "image/png",
        "width": 8,
        "height": 8,
    }
    images = []
    for position in (1, 2):
        filename = f"fixture-{position}.png"
        tmp_path.joinpath(filename).write_bytes(content)
        images.append({"file": filename, **metadata})
    return images


def test_demo_source_verifier_rejects_a_malformed_archive_derived_path(tmp_path) -> None:
    """Given a path-bearing fixture entry, validation stops before resource access."""
    images = verified_demo_images(tmp_path)
    images[0]["file"] = "../fixture-1.png"

    with pytest.raises(CommandError, match="이름이 안전하지"):
        _verify_sources(products=[{"images": images}], root=tmp_path)


def test_demo_source_verifier_rejects_a_checksum_mismatch(tmp_path) -> None:
    """Given tampered metadata, validation refuses the otherwise valid PNG bytes."""
    images = verified_demo_images(tmp_path)
    images[0]["sha256"] = "0" * 64

    with pytest.raises(CommandError, match="checksum 불일치"):
        _verify_sources(products=[{"images": images}], root=tmp_path)


def test_demo_source_verifier_rejects_a_dimension_mismatch(tmp_path) -> None:
    """Given incorrect dimensions, validation refuses the fixture before bootstrap."""
    images = verified_demo_images(tmp_path)
    images[0]["width"] = 9

    with pytest.raises(CommandError, match="dimensions 불일치"):
        _verify_sources(products=[{"images": images}], root=tmp_path)


def test_demo_source_verifier_rejects_an_oversized_metadata_declaration(tmp_path) -> None:
    """Given an oversized metadata declaration, validation refuses the fixture."""
    images = verified_demo_images(tmp_path)
    images[0]["byte_size"] = MAX_IMAGE_BYTES + 1

    with pytest.raises(CommandError, match="크기 metadata가 안전하지"):
        _verify_sources(products=[{"images": images}], root=tmp_path)


@pytest.mark.parametrize(
    ("image_format", "content_type", "suffix"),
    [("JPEG", "image/jpeg", "jpg"), ("PNG", "image/png", "png"), ("WEBP", "image/webp", "webp")],
)
def test_sanitizer_fully_decodes_and_uses_uuid_name(
    image_format: str, content_type: str, suffix: str
) -> None:
    upload = SimpleUploadedFile(f"source.{suffix}", image_bytes(image_format), content_type=content_type)

    sanitized = PillowProductImagePipeline().sanitize(upload=upload)

    assert UUID(sanitized.storage_name.removesuffix(f".{suffix}"), version=4)
    assert sanitized.content_type == content_type
    assert sanitized.byte_size == len(sanitized.content)
    with Image.open(BytesIO(sanitized.content)) as decoded:
        decoded.load()
        assert decoded.format == image_format
        assert decoded.size == (8, 8)
        assert not decoded.getexif()


def test_sanitizer_removes_png_text_metadata() -> None:
    output = BytesIO()
    metadata = PngImagePlugin.PngInfo()
    metadata.add_text("Comment", "must not survive")
    Image.new("RGB", (4, 4)).save(output, format="PNG", pnginfo=metadata)
    upload = SimpleUploadedFile("source.png", output.getvalue(), content_type="image/png")

    sanitized = PillowProductImagePipeline().sanitize(upload=upload)

    with Image.open(BytesIO(sanitized.content)) as decoded:
        assert "Comment" not in decoded.info


@pytest.mark.parametrize(
    ("name", "payload", "content_type"),
    [
        ("fake.png", image_bytes("JPEG"), "image/png"),
        ("attack.svg", b'<svg><script>alert(1)</script></svg>', "image/svg+xml"),
        ("broken.png", b"\x89PNG\r\n\x1a\nnot-an-image", "image/png"),
        ("polyglot.png", image_bytes("PNG") + b"<script>alert(1)</script>", "image/png"),
        pytest.param(
            "too-large.png",
            b"x" * (MAX_IMAGE_BYTES + 1),
            "image/png",
            id="too-large",
        ),
    ],
)
def test_sanitizer_rejects_disguised_corrupt_polyglot_and_oversized_inputs(
    name: str, payload: bytes, content_type: str
) -> None:
    upload = SimpleUploadedFile(name, payload, content_type=content_type)

    with pytest.raises(ValidationError):
        PillowProductImagePipeline().sanitize(upload=upload)


def test_sanitizer_rejects_over_dimension_image() -> None:
    upload = SimpleUploadedFile(
        "wide.png",
        image_bytes("PNG", size=(4097, 1)),
        content_type="image/png",
    )

    with pytest.raises(ValidationError):
        PillowProductImagePipeline().sanitize(upload=upload)


def test_sanitizer_rejects_path_storage_name() -> None:
    class PathUpload:
        name = "../escape.png"
        content_type = "image/png"

        def chunks(self):
            yield image_bytes("PNG")

    with pytest.raises(ValidationError):
        PillowProductImagePipeline().sanitize(upload=PathUpload())  # type: ignore[arg-type]
