from io import BytesIO
from pathlib import Path
from uuid import UUID

import pytest
from django.http import HttpResponse
from django.test import Client, override_settings
from django.urls import include, path, reverse
from PIL import Image

from apps.accounts.models import User
from apps.catalog.forms import ProductCreateForm
from apps.catalog.models import Product

urlpatterns = [path("products/", include("apps.catalog.urls"))]
pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def catalog_urls(settings) -> None:
    settings.ROOT_URLCONF = __name__


def png_upload():
    from django.core.files.uploadedfile import SimpleUploadedFile

    output = BytesIO()
    Image.new("RGB", (8, 8), "blue").save(output, format="PNG")
    return SimpleUploadedFile("source.png", output.getvalue(), content_type="image/png")


def create_product(owner: User, **changes: object) -> Product:
    values = {
        "title": "안전한 상품",
        "description": "상품 설명",
        "price": 10_000,
        "sale_state": Product.SaleState.AVAILABLE,
    }
    values.update(changes)
    return Product.objects.create(owner=owner, **values)


def force_login_with_epoch(client: Client, user: User) -> None:
    client.force_login(user)
    session = client.session
    session["account_auth_epoch"] = user.auth_epoch
    session.save()


def test_create_requires_authentication_and_csrf() -> None:
    assert Client().post(reverse("catalog:create")).status_code == 302

    user = User.objects.create_user(username="owner_01", password="long-password-123")
    csrf_client = Client(enforce_csrf_checks=True)
    force_login_with_epoch(csrf_client, user)
    assert csrf_client.post(reverse("catalog:create"), {}).status_code == 403


def test_owner_creates_product_with_sanitized_image(tmp_path: Path) -> None:
    user = User.objects.create_user(username="owner_01", password="long-password-123")
    client = Client()
    force_login_with_epoch(client, user)

    with override_settings(MEDIA_ROOT=tmp_path):
        response = client.post(
            reverse("catalog:create"),
            {
                "title": "카메라",
                "description": "정상 작동합니다.",
                "price": "25000",
                "sale_state": Product.SaleState.AVAILABLE,
                "image": png_upload(),
            },
        )
        product = Product.objects.get()
        stored_path = tmp_path / product.image.name

    assert response.status_code == 302
    assert product.owner == user
    assert product.price == 25_000
    assert product.image.name.startswith("product-images/")
    assert UUID(Path(product.image.name).stem, version=4)
    assert stored_path.is_file()


def test_price_and_image_are_required_on_create() -> None:
    form = ProductCreateForm(
        data={
            "title": "카메라",
            "description": "정상 작동합니다.",
            "price": "0",
            "sale_state": Product.SaleState.AVAILABLE,
        }
    )

    assert not form.is_valid()
    assert "price" in form.errors
    assert "image" in form.errors


def test_non_owner_cannot_update_or_delete_product() -> None:
    owner = User.objects.create_user(username="owner_01", password="long-password-123")
    attacker = User.objects.create_user(username="other_01", password="long-password-123")
    product = create_product(owner)
    client = Client()
    force_login_with_epoch(client, attacker)

    update = client.post(
        reverse("catalog:update", args=(product.pk,)),
        {
            "title": "탈취",
            "description": "권한 없음",
            "price": "1",
            "sale_state": Product.SaleState.SOLD,
            "version": product.version,
        },
    )
    delete = client.post(
        reverse("catalog:delete", args=(product.pk,)),
        {"version": product.version},
    )

    assert update.status_code == 404
    assert delete.status_code == 404
    product.refresh_from_db()
    assert product.title == "안전한 상품"


def test_owner_update_increments_optimistic_version() -> None:
    owner = User.objects.create_user(username="owner_01", password="long-password-123")
    product = create_product(owner)
    client = Client()
    force_login_with_epoch(client, owner)

    response = client.post(
        reverse("catalog:update", args=(product.pk,)),
        {
            "title": "수정된 상품",
            "description": "수정된 설명",
            "price": "12000",
            "sale_state": Product.SaleState.SOLD,
            "version": product.version,
        },
    )

    assert response.status_code == 302
    product.refresh_from_db()
    assert product.title == "수정된 상품"
    assert product.sale_state == Product.SaleState.SOLD
    assert product.version == 2


def test_stale_owner_update_is_rejected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    owner = User.objects.create_user(username="owner_01", password="long-password-123")
    product = create_product(owner, version=2)
    client = Client()
    force_login_with_epoch(client, owner)
    monkeypatch.setattr(
        "apps.catalog.views.render",
        lambda request, template, context, status=200: HttpResponse(status=status),
    )

    response = client.post(
        reverse("catalog:update", args=(product.pk,)),
        {
            "title": "덮어쓴 상품",
            "description": "오래된 요청",
            "price": "12000",
            "sale_state": Product.SaleState.SOLD,
            "version": 1,
        },
    )

    assert response.status_code == 409
    product.refresh_from_db()
    assert product.title == "안전한 상품"
    assert product.version == 2


def test_hidden_product_detail_is_public_404(monkeypatch: pytest.MonkeyPatch) -> None:
    owner = User.objects.create_user(username="owner_01", password="long-password-123")
    product = create_product(owner)
    monkeypatch.setattr("apps.catalog.views.is_product_public", lambda **_: False)

    response = Client().get(reverse("catalog:detail", args=(product.pk,)))

    assert response.status_code == 404
