from io import BytesIO
from uuid import UUID

import pytest
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from PIL import Image, PngImagePlugin

from apps.catalog.services import MAX_IMAGE_BYTES, PillowProductImagePipeline


def image_bytes(image_format: str = "PNG", *, size: tuple[int, int] = (8, 8)) -> bytes:
    output = BytesIO()
    image = Image.new("RGBA", size, (10, 20, 30, 255))
    if image_format == "JPEG":
        image = image.convert("RGB")
    image.save(output, format=image_format)
    return output.getvalue()


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
        ("too-large.png", b"x" * (MAX_IMAGE_BYTES + 1), "image/png"),
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
