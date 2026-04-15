"""Tests for variant inventory utils (Day 15)."""

from __future__ import annotations

from unittest.mock import MagicMock

from modules.inventory_online.variant_utils import (
    VariantGroupStock,
    VariantStock,
    group_variants,
    list_variants_by_filter,
    parse_variants_from_json,
)

# ── Test VariantStock ─────────────────────────────────────────────────────

class TestVariantStock:
    def test_out_of_stock(self):
        v = VariantStock(
            sku="VAR-S", ebay_item_id="I1",
            variant_specifics={"Size": "S"},
            quantity=0, price=100.0, status="OUT_OF_STOCK",
        )
        assert v.is_out_of_stock is True
        assert v.is_low_stock is False
        assert v.display_name == "Size: S"

    def test_low_stock(self):
        v = VariantStock(
            sku="VAR-M", ebay_item_id="I2",
            variant_specifics={"Size": "M"},
            quantity=2, price=100.0, status="LOW_STOCK",
        )
        assert v.is_out_of_stock is False
        assert v.is_low_stock is True

    def test_normal(self):
        v = VariantStock(
            sku="VAR-L", ebay_item_id="I3",
            variant_specifics={"Size": "L"},
            quantity=10, price=100.0, status="NORMAL",
        )
        assert v.is_out_of_stock is False
        assert v.is_low_stock is False

    def test_display_name_multiple(self):
        v = VariantStock(
            sku="VAR-XL", ebay_item_id="I4",
            variant_specifics={"Size": "XL", "Color": "Red"},
            quantity=5, price=120.0, status="NORMAL",
        )
        assert "Size: XL" in v.display_name
        assert "Color: Red" in v.display_name


# ── Test VariantGroupStock ─────────────────────────────────────────────────

class TestVariantGroupStock:
    def test_fully_out_of_stock(self):
        variants = [
            VariantStock("V1", "I1", {"Size": "S"}, 0, 100.0, "OUT_OF_STOCK"),
            VariantStock("V2", "I2", {"Size": "M"}, 0, 100.0, "OUT_OF_STOCK"),
        ]
        g = VariantGroupStock(
            group_id="GRP-1", parent_title="Test Shirt",
            variant_count=2, skus=["V1", "V2"],
            variants=variants, aggregate_status="FULLY_OUT_OF_STOCK",
        )
        assert g.aggregate_status == "FULLY_OUT_OF_STOCK"
        assert g.out_of_stock_count == 2
        assert g.total_quantity == 0
        assert g.out_of_stock_skus() == ["V1", "V2"]

    def test_partial_out_of_stock(self):
        variants = [
            VariantStock("V1", "I1", {"Size": "S"}, 0, 100.0, "OUT_OF_STOCK"),
            VariantStock("V2", "I2", {"Size": "M"}, 5, 100.0, "NORMAL"),
        ]
        g = VariantGroupStock(
            group_id="GRP-2", parent_title="Test Shirt",
            variant_count=2, skus=["V1", "V2"],
            variants=variants, aggregate_status="PARTIAL_OUT_OF_STOCK",
        )
        assert g.out_of_stock_count == 1
        assert g.total_quantity == 5
        assert g.out_of_stock_skus() == ["V1"]

    def test_normal_group(self):
        variants = [
            VariantStock("V1", "I1", {"Size": "S"}, 10, 100.0, "NORMAL"),
            VariantStock("V2", "I2", {"Size": "M"}, 8, 100.0, "NORMAL"),
        ]
        g = VariantGroupStock(
            group_id="GRP-3", parent_title="Test Shirt",
            variant_count=2, skus=["V1", "V2"],
            variants=variants, aggregate_status="NORMAL",
        )
        assert g.aggregate_status == "NORMAL"
        assert g.out_of_stock_count == 0


# ── Test parse_variants_from_json ────────────────────────────────────────

class TestParseVariantsFromJson:
    def test_valid_json(self):
        j = {"variant_specifics": {"Size": "M", "Color": "Red"}}
        assert parse_variants_from_json(j) == {"Size": "M", "Color": "Red"}

    def test_none_json(self):
        assert parse_variants_from_json(None) == {}

    def test_empty_json(self):
        assert parse_variants_from_json({}) == {}


# ── Test group_variants ──────────────────────────────────────────────────

class TestGroupVariants:
    def _mock_listing(self, sku, group_id, qty, specifics):
        m = MagicMock()
        m.sku = sku
        m.ebay_item_id = f"ITEM-{sku}"
        m.quantity_available = qty
        m.listing_price = 100.0
        m.variants = {
            "group_id": group_id,
            "variant_specifics": specifics,
            "siblings": ["SKU-S", "SKU-M", "SKU-L"],
            "total_variants": 3,
        }
        return m

    def test_groups_by_group_id(self):
        s_list = [
            self._mock_listing("SKU-S", "GRP-SHIRT", 0, {"Size": "S"}),
            self._mock_listing("SKU-M", "GRP-SHIRT", 5, {"Size": "M"}),
            self._mock_listing("SKU-L", "GRP-SHOES", 3, {"Size": "L"}),
        ]
        groups = group_variants(s_list)
        assert len(groups) == 2

        grp_shirt = next(g for g in groups if g.group_id == "GRP-SHIRT")
        assert grp_shirt.variant_count == 2
        assert grp_shirt.aggregate_status == "PARTIAL_OUT_OF_STOCK"

    def test_fully_out_of_stock_group(self):
        s_list = [
            self._mock_listing("SKU-S", "GRP-SOCKS", 0, {"Size": "S"}),
            self._mock_listing("SKU-M", "GRP-SOCKS", 0, {"Size": "M"}),
        ]
        groups = group_variants(s_list)
        grp = groups[0]
        assert grp.aggregate_status == "FULLY_OUT_OF_STOCK"
        assert grp.out_of_stock_count == 2

    def test_no_variants_field(self):
        m = MagicMock()
        m.sku = "NO-VAR-SKU"
        m.ebay_item_id = "I1"
        m.quantity_available = 10
        m.listing_price = 50.0
        m.variants = None
        groups = group_variants([m])
        assert len(groups) == 1
        assert groups[0].variant_count == 1


# ── Test list_variants_by_filter ─────────────────────────────────────────

class TestListVariantsByFilter:
    def _mock_listing(self, sku, qty, specifics):
        m = MagicMock()
        m.sku = sku
        m.ebay_item_id = f"ITEM-{sku}"
        m.quantity_available = qty
        m.listing_price = 100.0
        m.variants = {"variant_specifics": specifics} if specifics else None
        return m

    def test_filter_by_size_l(self):
        listings = [
            self._mock_listing("SKU-S", 0, {"Size": "S"}),
            self._mock_listing("SKU-M", 5, {"Size": "M"}),
            self._mock_listing("SKU-L", 0, {"Size": "L"}),
        ]
        results = list_variants_by_filter(listings, filter_dimension="Size", filter_value="L")
        assert len(results) == 1
        assert results[0].sku == "SKU-L"
        assert results[0].is_out_of_stock is True

    def test_filter_no_match(self):
        listings = [
            self._mock_listing("SKU-S", 5, {"Size": "S"}),
        ]
        results = list_variants_by_filter(listings, filter_dimension="Size", filter_value="XL")
        assert len(results) == 0

    def test_no_filter_returns_all(self):
        listings = [
            self._mock_listing("SKU-S", 0, {"Size": "S"}),
            self._mock_listing("SKU-M", 5, {"Size": "M"}),
        ]
        results = list_variants_by_filter(listings)
        assert len(results) == 2
