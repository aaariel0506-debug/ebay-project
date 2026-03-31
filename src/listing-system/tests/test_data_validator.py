"""
tests/test_data_validator.py — 数据校验器测试
"""
import pytest
import sys
from pathlib import Path

# 让 import 找到 listing-system 模块
sys.path.insert(0, str(Path(__file__).parent.parent))

from data_validator import validate_item, validate_batch, VALID_CONDITIONS, REQUIRED_FIELDS


def make_valid_item(**overrides):
    """生成一条合法的商品数据"""
    item = {
        "sku": "TEST-001",
        "title": "Hobonichi Techo 2026 Planner A6 English",
        "description": "Brand new Hobonichi Techo 2026 planner, A6 size, English edition. Ships from Japan.",
        "category_id": "172008",
        "price": 39.99,
        "quantity": 5,
        "image_urls": "https://example.com/img1.jpg, https://example.com/img2.jpg",
        "condition": "NEW",
    }
    item.update(overrides)
    return item


class TestValidateItem:
    """单条商品校验"""

    def test_valid_item_passes(self):
        result = validate_item(make_valid_item())
        assert result.valid is True
        assert result.errors == []

    def test_missing_required_field(self):
        for field in REQUIRED_FIELDS:
            item = make_valid_item(**{field: ""})
            result = validate_item(item)
            assert result.valid is False, f"Should fail when {field} is empty"

    def test_missing_sku_shows_empty_label(self):
        item = make_valid_item(sku="")
        result = validate_item(item)
        assert result.sku == "(empty)"

    def test_invalid_sku_format(self):
        result = validate_item(make_valid_item(sku="BAD SKU WITH SPACES"))
        assert result.valid is False
        assert any("SKU 格式" in e for e in result.errors)

    def test_title_too_short(self):
        result = validate_item(make_valid_item(title="Hi"))
        assert result.valid is False
        assert any("标题太短" in e for e in result.errors)

    def test_title_too_long_warns(self):
        long_title = "A" * 100
        result = validate_item(make_valid_item(title=long_title))
        assert result.valid is True  # warning, not error
        assert any("标题超过" in w for w in result.warnings)

    def test_negative_price(self):
        result = validate_item(make_valid_item(price=-10))
        assert result.valid is False
        assert any("价格必须大于 0" in e for e in result.errors)

    def test_zero_quantity(self):
        result = validate_item(make_valid_item(quantity=0))
        assert result.valid is False

    def test_invalid_category_id(self):
        result = validate_item(make_valid_item(category_id="abc"))
        assert result.valid is False
        assert any("分类 ID" in e for e in result.errors)

    def test_invalid_image_url(self):
        result = validate_item(make_valid_item(image_urls="not-a-url"))
        assert result.valid is False

    def test_unknown_condition_warns(self):
        result = validate_item(make_valid_item(condition="MINT"))
        assert result.valid is True
        assert any("condition" in w for w in result.warnings)

    def test_valid_conditions_map(self):
        assert "NEW" in VALID_CONDITIONS
        assert VALID_CONDITIONS["NEW"] == "1000"


class TestValidateBatch:
    """批量校验"""

    def test_batch_all_valid(self):
        items = [make_valid_item(sku=f"SKU-{i}") for i in range(3)]
        results = validate_batch(items)
        assert all(r.valid for r in results)

    def test_batch_detects_duplicate_sku(self):
        items = [make_valid_item(sku="DUPE"), make_valid_item(sku="DUPE")]
        results = validate_batch(items)
        assert results[1].valid is False
        assert any("重复" in e for e in results[1].errors)

    def test_batch_mixed_results(self):
        items = [
            make_valid_item(sku="GOOD-1"),
            make_valid_item(sku="", title=""),  # invalid
        ]
        results = validate_batch(items)
        assert results[0].valid is True
        assert results[1].valid is False
