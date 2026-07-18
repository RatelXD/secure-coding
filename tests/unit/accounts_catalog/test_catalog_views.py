from io import BytesIO
from pathlib import Path
from uuid import UUID

import pytest
from django.http import HttpResponse
from django.test import Client, TestCase, override_settings
from django.urls import include, path, reverse
from PIL import Image

from apps.accounts.models import User
from apps.catalog.forms import ProductCreateForm
from apps.catalog.models import Product, Region

urlpatterns = [
    path("", lambda request: HttpResponse(), name="home"),
    path("products/", include("apps.catalog.urls")),
]
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


@override_settings(ROOT_URLCONF="config.urls")
def test_product_list_region_filter_is_exact_and_fails_closed() -> None:
    owner = User.objects.create_user(username="region_owner", password="long-password-123")
    region = Region.objects.create(code="SEOUL-JONGNO", label="서울특별시 종로구")
    other_region = Region.objects.create(code="BUSAN-HAEUNDAE", label="부산광역시 해운대구")
    legacy = create_product(owner, title="지역 미설정", region=None)
    selected = create_product(
        owner,
        title="서울 상품",
        region=region,
        region_source=Product.RegionSource.SELECTED,
    )
    other = create_product(
        owner,
        title="부산 상품",
        region=other_region,
        region_source=Product.RegionSource.SELECTED,
    )
    client = Client()

    omitted = client.get(reverse("catalog:list"))
    assert omitted.status_code == 200
    assert {product.pk for product in omitted.context["products"]} == {
        legacy.pk,
        selected.pk,
        other.pk,
    }
    assert len(omitted.context["products"]) == 3
    assert omitted.context["region_error"] is False

    selected_response = client.get(reverse("catalog:list"), {"region": region.code})
    assert selected_response.status_code == 200
    assert [product.pk for product in selected_response.context["products"]] == [selected.pk]
    assert len(selected_response.context["products"]) == 1
    assert selected_response.context["selected_region_code"] == region.code

    invalid = client.get(reverse("catalog:list"), {"region": "owner__username"})
    assert invalid.status_code == 200
    assert invalid.context["products"] == []
    assert len(invalid.context["products"]) == 0
    assert invalid.context["region_error"] is True
    assert "선택할 수 없는 지역입니다" in invalid.content.decode()

    multiple = client.get(reverse("catalog:list"), [("region", region.code), ("region", region.code)])
    assert multiple.status_code == 200
    assert multiple.context["products"] == []
    assert len(multiple.context["products"]) == 0
    assert multiple.context["region_error"] is True


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
        with TestCase.captureOnCommitCallbacks(execute=True):
            response = client.post(
                reverse("catalog:create"),
                {
                    "title": "카메라",
                    "description": "정상 작동합니다.",
                    "price": "25000",
                    "sale_state": Product.SaleState.AVAILABLE,
                    "category": "OTHER",
                    "region": "",
                    "images": png_upload(),
                },
            )
        product = Product.objects.get()
        product_image = product.images.get()
        product_image.refresh_from_db()
        stored_path = tmp_path / product_image.image.name
    assert response.status_code == 302
    assert product.owner == user
    assert product.price == 25_000
    assert not product.image
    assert product_image.image.name.startswith(f"product-images/owned/{product.pk}/")
    assert UUID(Path(product_image.image.name).stem, version=4)
    assert stored_path.is_file()


def test_price_is_required_and_images_are_optional_on_create() -> None:
    form = ProductCreateForm(
        data={
            "title": "카메라",
            "description": "정상 작동합니다.",
            "price": "0",
            "category": "OTHER",
            "region": "",
        }
    )

    assert not form.is_valid()
    assert "price" in form.errors
    assert "images" not in form.errors


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
            "category": "OTHER",
            "region": "",
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
            "category": "OTHER",
            "region": "",
            "sale_state": Product.SaleState.SOLD,
            "version": product.version,
        },
    )

    assert response.status_code == 302
    product.refresh_from_db()
    assert product.title == "수정된 상품"
    assert product.sale_state == Product.SaleState.AVAILABLE
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
            "category": "OTHER",
            "region": "",
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
