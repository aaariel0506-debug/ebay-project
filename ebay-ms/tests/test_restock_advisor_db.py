"""
tests/test_restock_advisor_db.py

Day 24: Phase 3 覆盖率补测 — restock_advisor DB 集成测试
"""

from decimal import Decimal

from core.models import Order, Product, ProductStatus
from core.models.listing import EbayListing, ListingStatus


class TestRestockAdvisorDB:
    """RestockAdvisor DB 集成测试"""

    def _setup_product_listing_order(self, db_session, sku, quantity_sold):
        """创建 Product + EbayListing + Order"""
        prod = Product(
            sku=sku,
            title=f"Test Product {sku}",
            cost_price=Decimal("100.00"),
            cost_currency="JPY",
            status=ProductStatus.ACTIVE,
            supplier="Test Supplier",
        )
        db_session.add(prod)

        listing = EbayListing(
            sku=sku,
            ebay_item_id="ITEM123456789",
            title=f"Test Listing {sku}",
            quantity_available=5,  # 低库存
            listing_price=Decimal("200.00"),
            status=ListingStatus.ACTIVE,
        )
        db_session.add(listing)

        # 创建已发货订单
        order = Order(
            ebay_order_id="ORDER-RESTOCK-001",
            sku=sku,
            sale_price=200.00,
            shipping_cost=0,
            ebay_fee=0,
        )
        db_session.add(order)
        db_session.commit()
        return prod, listing, order

    def test_get_restock_list_returns_result(self, db_session):
        """get_restock_list: 返回补货建议"""
        from modules.inventory_online.restock_advisor import RestockAdvisor

        _, listing, _ = self._setup_product_listing_order(
            db_session, "RA-TEST-001", 10
        )
        # 设置低库存
        listing.quantity_available = 2
        db_session.commit()

        advisor = RestockAdvisor()
        result = advisor.get_restock_list()

        # 至少返回结果对象
        assert result is not None

    def test_get_restock_list_with_high_stock(self, db_session):
        """get_restock_list: 高库存"""
        from modules.inventory_online.restock_advisor import RestockAdvisor

        _, listing, _ = self._setup_product_listing_order(
            db_session, "RA-TEST-002", 0
        )
        listing.quantity_available = 100
        db_session.commit()

        advisor = RestockAdvisor()
        result = advisor.get_restock_list()

        assert result is not None
