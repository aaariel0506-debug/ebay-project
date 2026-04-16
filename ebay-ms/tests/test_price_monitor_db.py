"""
tests/test_price_monitor_db.py

Day 24: Phase 3 覆盖率补测 — price_monitor DB 集成测试
"""

from decimal import Decimal

import pytest
from core.models import Product, ProductStatus, SupplierPriceHistory
from core.models.listing import EbayListing, ListingStatus


class TestPriceMonitorDB:
    """PriceMonitor DB 集成测试"""

    def _setup_product_and_listing(self, db_session, sku, cost_price, listing_price):
        """创建 Product + EbayListing"""
        prod = Product(
            sku=sku,
            title=f"Test Product {sku}",
            cost_price=cost_price,
            cost_currency="JPY",
            status=ProductStatus.ACTIVE,
            supplier="Test Supplier",
        )
        db_session.add(prod)

        listing = EbayListing(
            sku=sku,
            ebay_item_id="ITEM123456789",
            title=f"Test Listing {sku}",
            quantity_available=10,
            listing_price=listing_price,
            status=ListingStatus.ACTIVE,
        )
        db_session.add(listing)
        db_session.commit()
        return prod, listing

    def test_update_cost_price_creates_history_record(self, db_session):
        """update_cost_price: 旧价格写入 history 表"""
        from modules.inventory_online.price_monitor import PriceMonitor

        _, listing = self._setup_product_and_listing(
            db_session, "PM-TEST-001", Decimal("100.00"), Decimal("200.00")
        )

        # 先更新一次成本价（从 100 → 120）
        monitor = PriceMonitor()
        monitor.update_cost_price("PM-TEST-001", Decimal("120.00"))

        # 验证 history 表有记录
        history = (
            db_session.query(SupplierPriceHistory)
            .filter(SupplierPriceHistory.sku == "PM-TEST-001")
            .all()
        )
        assert len(history) == 1
        assert history[0].price == Decimal("100.00")  # 旧价格写入

    def test_update_cost_price_updates_product(self, db_session):
        """update_cost_price: Product 表更新"""
        from modules.inventory_online.price_monitor import PriceMonitor

        prod, _ = self._setup_product_and_listing(
            db_session, "PM-TEST-002", Decimal("100.00"), Decimal("200.00")
        )

        monitor = PriceMonitor()
        monitor.update_cost_price("PM-TEST-002", Decimal("150.00"))

        db_session.refresh(prod)
        assert prod.cost_price == Decimal("150.00")

    def test_update_cost_price_no_change_records_history(self, db_session):
        """update_cost_price: 价格不变也写 history（当前行为）"""
        from modules.inventory_online.price_monitor import PriceMonitor

        _, _ = self._setup_product_and_listing(
            db_session, "PM-TEST-003", Decimal("100.00"), Decimal("200.00")
        )

        monitor = PriceMonitor()
        monitor.update_cost_price("PM-TEST-003", Decimal("100.00"))

        history = (
            db_session.query(SupplierPriceHistory)
            .filter(SupplierPriceHistory.sku == "PM-TEST-003")
            .all()
        )
        assert len(history) == 1
        assert history[0].price == Decimal("100.00")

    def test_update_cost_price_nonexistent_sku_raises(self, db_session):
        """update_cost_price: 不存在的 SKU 抛异常"""
        from modules.inventory_online.price_monitor import PriceMonitor

        monitor = PriceMonitor()
        with pytest.raises(ValueError, match="SKU 不存在"):
            monitor.update_cost_price("NONEXISTENT-SKU", Decimal("100.00"))
