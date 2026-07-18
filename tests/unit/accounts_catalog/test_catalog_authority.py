from datetime import timedelta

from django.apps import apps as django_apps
import pytest
from django.db import IntegrityError, transaction
from django.db.models.signals import post_migrate
from django.test import Client, override_settings
from django.urls import include, path, reverse
from django.utils import timezone

from apps.accounts.models import User
from apps.catalog.forms import ProductCreateForm
from apps.catalog.models import CATEGORY_CHOICES, Category, Product, Region
from apps.catalog.projectors import ProductState, effective_product_state, legacy_trade_is_review_eligible
from apps.trades.models import Trade

pytestmark = pytest.mark.django_db
urlpatterns = [path("products/", include("apps.catalog.urls"))]


@pytest.fixture(autouse=True)
def catalog_urls(settings) -> None:
    settings.ROOT_URLCONF = __name__




EXPECTED_CATEGORY_CODES = {
    "DIGITAL_APPLIANCES",
    "LIVING_KITCHEN",
    "FURNITURE_INTERIOR",
    "FASHION_GOODS",
    "SPORTS_HOBBIES",
    "BOOKS",
    "OTHER",
}


def _owner() -> User:
    return User.objects.create_user(username="authority_owner", password="long-password-123")

def _force_login(client: Client, user: User) -> None:
    client.force_login(user)
    session = client.session
    session["account_auth_epoch"] = user.auth_epoch
    session.save()



def _category() -> Category:
    return Category.objects.order_by("display_order").first()


def _product(owner: User, **changes: object) -> Product:
    values: dict[str, object] = {
        "owner": owner,
        "title": "권위 상품",
        "description": "권위 경계 검증",
        "price": 10_000,
        "category": _category(),
    }
    values.update(changes)
    return Product.objects.create(**values)


def test_category_seed_is_exactly_the_approved_seven_values() -> None:
    """G7A-CAT-REF-001: 분류 seed와 공개 선택지는 승인된 일곱 값뿐이다."""
    assert {code for code, _label in CATEGORY_CHOICES} == EXPECTED_CATEGORY_CODES
    assert set(Category.objects.values_list("code", flat=True)) == EXPECTED_CATEGORY_CODES
    assert Category.objects.count() == 7
def test_product_form_omission_uses_canonical_other_and_allows_blank_region() -> None:
    """G7A-CAT-REF-002: 입력 생략은 정확한 OTHER 권위값으로만 보정한다."""
    form = ProductCreateForm(
        data={
            "title": "생략 호환 상품",
            "description": "기존 요청 형식 호환",
            "price": "10000",
            "region": "",
        }
    )

    assert form.is_valid()
    assert form.cleaned_data["category"].code == "OTHER"
    assert form.cleaned_data["region"] is None


def test_create_and_update_set_region_source_from_optional_region() -> None:
    """G7A-CAT-REGION-003: 생성·수정 모두 빈 지역은 LEGACY_UNSET으로 저장한다."""
    owner = _owner()
    region = Region.objects.create(code="TEST-REGION", label="테스트시 테스트구")
    client = Client()
    _force_login(client, owner)

    create = client.post(
        reverse("catalog:create"),
        {
            "title": "지역 선택 상품",
            "description": "선택 지역 검증",
            "price": "10000",
            "category": "OTHER",
            "region": region.code,
        },
    )

    assert create.status_code == 302
    product = Product.objects.get()
    assert product.region == region
    assert product.region_source == Product.RegionSource.SELECTED

    update = client.post(
        reverse("catalog:update", args=(product.pk,)),
        {
            "title": "지역 해제 상품",
            "description": "빈 지역 검증",
            "price": "10000",
            "region": "",
            "version": product.version,
        },
    )

    assert update.status_code == 302
    product.refresh_from_db()
    assert product.category_id == "OTHER"
    assert product.region is None
    assert product.region_source == Product.RegionSource.LEGACY_UNSET


def test_category_reseed_signal_is_test_only_and_idempotent() -> None:
    """G7A-CAT-REF-003: 등록된 signal은 명시적인 테스트 경계에서만 canonical rows를 복구한다."""
    catalog_config = django_apps.get_app_config("catalog")
    other = Category.objects.get(pk="OTHER")
    other.label = "보존할 운영 라벨"
    other.save(update_fields=["label"])

    with override_settings(CATALOG_RESEED_CATEGORIES_FOR_TESTS=False):
        post_migrate.send(
            sender=catalog_config,
            app_config=catalog_config,
            using="default",
            plan=[],
            interactive=False,
            verbosity=0,
            apps=django_apps,
        )
    other.refresh_from_db()
    assert other.label == "보존할 운영 라벨"

    Category.objects.all().delete()
    with override_settings(CATALOG_RESEED_CATEGORIES_FOR_TESTS=True):
        post_migrate.send(
            sender=catalog_config,
            app_config=catalog_config,
            using="default",
            plan=[],
            interactive=False,
            verbosity=0,
            apps=django_apps,
        )
        first_ids = dict(Category.objects.values_list("code", "pk"))
        post_migrate.send(
            sender=catalog_config,
            app_config=catalog_config,
            using="default",
            plan=[],
            interactive=False,
            verbosity=0,
            apps=django_apps,
        )

    assert set(first_ids) == EXPECTED_CATEGORY_CODES
    assert dict(Category.objects.values_list("code", "pk")) == first_ids
    product = Product.objects.create(
        owner=_owner(),
        title="기본 분류 상품",
        description="모델 기본값 검증",
        price=10_000,
    )
    assert product.category_id == "OTHER"



def test_legacy_unset_region_is_included_without_filter_and_excluded_with_filter() -> None:
    """G7A-CAT-REGION-001: 레거시 NULL은 전체에는 포함되고 특정 지역 필터에는 제외된다."""
    owner = _owner()
    region = Region.objects.create(code="TEST-REGION", label="테스트시 테스트구")
    legacy = _product(owner, region=None, region_source=Product.RegionSource.LEGACY_UNSET)
    selected = _product(
        owner,
        title="지역 선택 상품",
        region=region,
        region_source=Product.RegionSource.SELECTED,
    )

    assert set(Product.objects.values_list("pk", flat=True)) == {legacy.pk, selected.pk}
    assert list(Product.objects.filter(region=region).values_list("pk", flat=True)) == [selected.pk]


@pytest.mark.parametrize(
    ("region_source", "with_region"),
    [
        (Product.RegionSource.LEGACY_UNSET, True),
        (Product.RegionSource.SELECTED, False),
        (Product.RegionSource.INHERITED, False),
    ],
)
def test_region_source_and_nullable_region_must_agree(region_source: str, with_region: bool) -> None:
    """G7A-CAT-REGION-002: LEGACY_UNSET/SELECTED/INHERITED 조합은 DB가 강제한다."""
    owner = _owner()
    region = Region.objects.create(code="TEST-REGION", label="테스트시 테스트구")

    with pytest.raises(IntegrityError), transaction.atomic():
        _product(owner, region=region if with_region else None, region_source=region_source)


def test_effective_state_ignores_frozen_legacy_sale_state_without_trade() -> None:
    """G7A-CAT-PROJECTOR-001: 읽기 권위는 compatibility sale_state가 아니라 Trade다."""
    product = _product(_owner(), sale_state=Product.SaleState.SOLD)

    assert effective_product_state(product=product, db_now=timezone.now()) is ProductState.AVAILABLE


def test_typed_legacy_sold_trade_projects_sold_without_buyer_or_review() -> None:
    """G7A-CAT-PROJECTOR-002: legacy SOLD는 buyer 없는 typed terminal Trade로만 투영한다."""
    product = _product(_owner())
    completed_at = timezone.now() - timedelta(days=1)
    trade = Trade.objects.create(
        product=product,
        seller=product.owner,
        buyer=None,
        kind=Trade.Kind.LEGACY_SOLD,
        status=Trade.Status.COMPLETED,
        completed_at=completed_at,
    )

    assert effective_product_state(product=product, db_now=timezone.now()) is ProductState.SOLD
    assert trade.buyer_id is None
    assert not legacy_trade_is_review_eligible(trade=trade)


def test_projector_requires_database_time_boundary() -> None:
    """G7A-CAT-PROJECTOR-003: 호출자가 암묵적 application clock을 사용할 수 없다."""
    product = _product(_owner())

    with pytest.raises(ValueError, match="timezone-aware"):
        effective_product_state(product=product, db_now=timezone.now().replace(tzinfo=None))
