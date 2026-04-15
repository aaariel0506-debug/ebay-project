"""Tests for ListingTemplate CRUD and template service."""

from __future__ import annotations

import uuid
from unittest.mock import MagicMock

import pytest
from core.database.connection import get_session
from core.models.template import ListingTemplate
from modules.listing.template_service import TemplateError, TemplateService

# ── Fixtures ────────────────────────────────────────────────────────────────

@pytest.fixture
def ts() -> TemplateService:
    return TemplateService()


@pytest.fixture
def sample_template_data() -> dict:
    _uid = uuid.uuid4().hex[:8]
    return {
        "name": f"日本动漫手办-{_uid}",
        "description_template": "高品质 {title}，品牌：{brand}，状态：{condition}",
        "category_id": "257777",
        "condition": "NEW",
        "condition_description": "全新未拆封",
        "shipping_policy_id": "policy-shipping-001",
        "return_policy_id": "policy-return-001",
        "payment_policy_id": "policy-payment-001",
        "default_price_markup": 1.25,
        "image_settings": {"primary_index": 0, "secondary_urls": []},
        "is_default": False,
        "notes": "动漫手办专用模板",
    }


# ── Test TemplateService.create_template ───────────────────────────────────

class TestTemplateCreate:
    def test_create_minimal(self, ts: TemplateService):
        tpl = ts.create_template(name=f"test-minimal-{uuid.uuid4().hex[:8]}")
        assert tpl.name.startswith("test-minimal-")
        assert tpl.id is not None
        assert tpl.is_default is False
        assert tpl.created_at is not None

    def test_create_full(self, ts: TemplateService, sample_template_data: dict):
        tpl = ts.create_template(**sample_template_data)
        assert tpl.name == sample_template_data["name"]
        assert tpl.description_template == sample_template_data["description_template"]
        assert tpl.category_id == sample_template_data["category_id"]
        assert tpl.condition == sample_template_data["condition"]
        assert tpl.default_price_markup == sample_template_data["default_price_markup"]
        assert tpl.image_settings == sample_template_data["image_settings"]
        assert tpl.is_default is False

    def test_create_duplicate_name_raises(self, ts: TemplateService):
        _uid = uuid.uuid4().hex[:8]
        ts.create_template(name=f"dup-test-{_uid}")
        with pytest.raises(TemplateError, match="已存在"):
            ts.create_template(name=f"dup-test-{_uid}")

    def test_create_sets_default(self, ts: TemplateService, sample_template_data: dict):
        sample_template_data["is_default"] = True
        _data2_uid = uuid.uuid4().hex[:8]
        tpl = ts.create_template(**sample_template_data)
        assert tpl.is_default is True

        # 第二个设为 default，第一个自动取消
        data2 = sample_template_data.copy()
        data2["name"] = f"第二模板-{uuid.uuid4().hex[:8]}"
        data2["is_default"] = True
        tpl2 = ts.create_template(**data2)

        assert tpl2.is_default is True
        # 第一个应该已被取消
        refreshed = ts.get_template(tpl.id)
        assert refreshed.is_default is False

    def test_create_without_optional_fields(self, ts: TemplateService):
        tpl = ts.create_template(
            name=f"optionals-none-{uuid.uuid4().hex[:8]}",
            description_template=None,
            category_id=None,
            default_price_markup=None,
            image_settings=None,
        )
        assert tpl.description_template is None
        assert tpl.category_id is None
        assert tpl.default_price_markup is None


# ── Test TemplateService.list_templates ─────────────────────────────────────

class TestTemplateList:
    def test_list_empty(self, ts: TemplateService):
        # 清理可能残留
        with get_session() as sess:
            sess.query(ListingTemplate).filter(
                ListingTemplate.name.like("list-test-%")
            ).delete()
            sess.commit()

        uid = uuid.uuid4().hex[:8]
        name = f"list-empty-{uid}"
        ts.create_template(name=name)
        all_templates = ts.list_templates()
        names = [t.name for t in all_templates]
        assert name in names

    def test_list_returns_all(self, ts: TemplateService):
        uid = uuid.uuid4().hex[:8]
        names = [f"list-test-a-{uid}", f"list-test-b-{uid}"]
        for n in names:
            ts.create_template(name=n)
        result = ts.list_templates()
        names_found = [t.name for t in result if any(n in t.name for n in names)]
        assert set(names_found) == set(names)


# ── Test TemplateService.get_template ───────────────────────────────────────

class TestTemplateGet:
    def test_get_exists(self, ts: TemplateService):
        created = ts.create_template(name=f"get-test-{uuid.uuid4().hex[:8]}")
        fetched = ts.get_template(created.id)
        assert fetched.id == created.id
        assert fetched.name.startswith("get-test-")

    def test_get_not_exists_raises(self, ts: TemplateService):
        with pytest.raises(TemplateError, match="不存在"):
            ts.get_template("not-a-real-id")


# ── Test TemplateService.update_template ────────────────────────────────────

class TestTemplateUpdate:
    def test_update_name(self, ts: TemplateService):
        tpl = ts.create_template(name=f"update-old-{uuid.uuid4().hex[:8]}")
        updated = ts.update_template(tpl.id, name=f"update-new-{uuid.uuid4().hex[:8]}")
        assert updated.name.startswith("update-new-")

    def test_update_partial_fields(self, ts: TemplateService, sample_template_data: dict):
        pass  # name already set by fixture
        tpl = ts.create_template(**sample_template_data)
        # 只更新 category_id
        updated = ts.update_template(tpl.id, category_id="999999")
        assert updated.category_id == "999999"
        # 其他字段保持不变
        assert updated.condition == sample_template_data["condition"]
        assert updated.default_price_markup == sample_template_data["default_price_markup"]

    def test_update_not_exists_raises(self, ts: TemplateService):
        with pytest.raises(TemplateError, match="不存在"):
            ts.update_template("fake-id", name="x")


# ── Test TemplateService.delete_template ───────────────────────────────────

class TestTemplateDelete:
    def test_delete_exists(self, ts: TemplateService):
        tpl = ts.create_template(name="delete-me")
        ts.delete_template(tpl.id)
        with pytest.raises(TemplateError, match="不存在"):
            ts.get_template(tpl.id)

    def test_delete_not_exists_raises(self, ts: TemplateService):
        with pytest.raises(TemplateError, match="不存在"):
            ts.delete_template("fake-id")


# ── Test ListingTemplate.apply_placeholder ─────────────────────────────────

class TestPlaceholder:
    def test_apply_placeholder_basic(self):
        tpl = ListingTemplate(
            name="test",
            description_template="{title} - 品牌: {brand}, 尺码: {size}, 颜色: {color}",
        )
        result = tpl.apply_placeholder(
            title="Eternal Beat figures",
            brand="Aniplex",
            size="M",
            color="Red",
        )
        assert result == "Eternal Beat figures - 品牌: Aniplex, 尺码: M, 颜色: Red"

    def test_apply_placeholder_missing_values(self):
        tpl = ListingTemplate(
            name="test",
            description_template="{title}, {brand}, {size}, {color}",
        )
        result = tpl.apply_placeholder(title="My Product")
        assert result == "My Product, , , "

    def test_apply_placeholder_none_description(self):
        tpl = ListingTemplate(name="test", description_template=None)
        assert tpl.apply_placeholder(title="X") is None

    def test_apply_placeholder_no_match(self):
        tpl = ListingTemplate(name="test", description_template="{title} is great")
        result = tpl.apply_placeholder(title="Box")
        assert result == "Box is great"


# ── Test TemplateService.apply_template ───────────────────────────────────

class TestApplyTemplate:
    def test_apply_template_basic(self, ts: TemplateService, sample_template_data: dict):
        sample_template_data["name"] = f"apply-test-{uuid.uuid4().hex[:8]}"
        tpl = ts.create_template(**sample_template_data)

        mock_product = MagicMock()
        mock_product.sku = "FIG-001"
        mock_product.title = "Miku Hatsune"
        mock_product.brand = "Good Smile Company"
        mock_product.location_key = "warehouse-tokyo"

        request = ts.apply_template(
            template_id=tpl.id,
            product=mock_product,
            price=3500.0,
            quantity=5,
        )

        assert request.sku == "FIG-001"
        assert request.title == "Miku Hatsune"
        assert request.listing_price == 3500.0
        assert request.condition == "NEW"
        assert request.category_id == sample_template_data["category_id"]
        # 描述中占位符应被替换
        assert "Miku Hatsune" in (request.description or "")
        assert "Good Smile Company" in (request.description or "")
        assert request.fulfillment_policy_id == sample_template_data["shipping_policy_id"]

    def test_apply_template_with_condition_override(self, ts: TemplateService):
        tpl = ts.create_template(
            name=f"test-cond-{uuid.uuid4().hex[:8]}",
            condition="NEW",
        )
        mock_product = MagicMock()
        mock_product.sku = "X"
        mock_product.title = "X"
        mock_product.brand = ""
        mock_product.location_key = "loc"

        request = ts.apply_template(
            template_id=tpl.id,
            product=mock_product,
            price=1000.0,
            quantity=1,
            condition="USED_GOOD",
        )
        # 传入 condition 时应覆盖模板默认值
        assert request.condition == "USED_GOOD"

    def test_apply_template_policy_ids(self, ts: TemplateService, sample_template_data: dict):
        sample_template_data["name"] = f"apply-policy-{uuid.uuid4().hex[:8]}"
        tpl = ts.create_template(**sample_template_data)
        mock_product = MagicMock()
        mock_product.sku = "SKU"
        mock_product.title = "T"
        mock_product.brand = ""
        mock_product.location_key = "loc"

        request = ts.apply_template(
            template_id=tpl.id,
            product=mock_product,
            price=2000.0,
            quantity=2,
        )
        assert request.payment_policy_id == "policy-payment-001"
        assert request.return_policy_id == "policy-return-001"
        assert request.fulfillment_policy_id == "policy-shipping-001"

    def test_apply_template_invalid_template_raises(self, ts: TemplateService):
        mock_product = MagicMock()
        mock_product.sku = "X"
        mock_product.title = "X"
        with pytest.raises(TemplateError, match="不存在"):
            ts.apply_template(
                template_id="fake-id",
                product=mock_product,
                price=100.0,
                quantity=1,
            )


# ── Test TemplateService.from_existing ─────────────────────────────────────

class TestFromExisting:
    def test_from_existing_inventory_api(self, ts: TemplateService):
        mock_client = MagicMock()
        mock_client.get.return_value = {
            "categoryId": "CAT123",
            "condition": "NEW",
            "conditionDescription": "Brand new item",
            "listingPolicies": {
                "paymentPolicyId": "pay-001",
                "returnPolicyId": "ret-001",
                "fulfillmentPolicyId": "ship-001",
            },
            "description": "Item description template: {title}",
        }

        tpl = ts.from_existing(
            ebay_item_id="item-abc",
            template_name=f"from-existing-test-{uuid.uuid4().hex[:8]}",
            client=mock_client,
        )

        assert tpl.name.startswith("from-existing-test-")
        assert tpl.category_id == "CAT123"
        assert tpl.condition == "NEW"
        assert tpl.condition_description == "Brand new item"
        assert tpl.payment_policy_id == "pay-001"
        assert tpl.return_policy_id == "ret-001"
        assert tpl.shipping_policy_id == "ship-001"
        assert "Item description template" in (tpl.description_template or "")

    def test_from_existing_browse_api_fallback(self, ts: TemplateService):
        mock_client = MagicMock()
        # Inventory API 失败，触发 Browse API fallback
        from core.ebay_api.exceptions import EbayApiError

        mock_client.get.side_effect = EbayApiError("not found", status_code=404)
        mock_client.get.return_value = {
            "condition": "USED",
            "shortDescription": "Used item",
        }

        # Browse API 返回不含 listingPolicies，用 get.return_value
        # 需要第二次调用才返回 Browse 数据
        mock_client.get.side_effect = [
            EbayApiError("not found", status_code=404),
            {"condition": "USED", "shortDescription": "Used item"},
        ]

        tpl = ts.from_existing(
            ebay_item_id="item-xyz",
            template_name=f"browse-fallback-test-{uuid.uuid4().hex[:8]}",
            client=mock_client,
        )
        assert tpl.condition == "USED"
