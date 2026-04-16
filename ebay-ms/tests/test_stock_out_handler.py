"""
tests/test_stock_out_handler.py

Day 22: 线上线下库存联动 — STOCK_OUT 事件处理器测试
"""

from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest
from core.events.bus import get_event_bus
from core.events.models import EventLog, EventStatus
from core.models import EbayListing, Product, ProductStatus
from core.models.listing import ListingStatus

# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def event_bus():
    """重置 EventBus 单例，返回 fresh instance"""
    import core.events.bus as bus_module
    bus_module._event_bus_instance = None
    bus = get_event_bus()
    bus._handlers.clear()
    yield bus
    bus_module._event_bus_instance = None


@pytest.fixture
def mock_ebay_client():
    """Mock EbayClient.put 防止真实 API 调用"""
    with patch("core.ebay_api.client.EbayClient") as MockClient:
        mock_instance = MagicMock()
        mock_instance.put.return_value = MagicMock(status_code=204)
        MockClient.return_value = mock_instance
        yield mock_instance


@pytest.fixture
def setup_listing(db_session):
    """创建 Product + EbayListing（quantity_available=10）"""
    prod = Product(
        sku="HANDLER-TEST-001",
        title="Handler Test Product",
        cost_price=Decimal("500.00"),
        cost_currency="JPY",
        status=ProductStatus.ACTIVE,
        supplier="Test Supplier",
    )
    db_session.add(prod)

    listing = EbayListing(
        sku="HANDLER-TEST-001",
        ebay_item_id="ITEM123456789",
        title="Handler Test Listing",
        quantity_available=10,
        listing_price=Decimal("1500.00"),
        status=ListingStatus.ACTIVE,
    )
    db_session.add(listing)
    db_session.commit()
    return listing


# ── Tests ─────────────────────────────────────────────────────────────────────

class TestHandleStockOut:
    """STOCK_OUT 事件处理器测试"""

    def _stock_out(self, event_bus, db_session, sku, quantity, related_order=None):
        """发布 STOCK_OUT，不依赖 publish() 返回值，直接查 DB"""
        payload = {
            "sku": sku,
            "quantity": quantity,
            "related_order": related_order or "ORDER-TEST-001",
            "operator": "test",
            "occurred_at": "2026-04-16T10:00:00Z",
        }
        # 记录发布前最新的 event id
        before = (
            db_session.query(EventLog.id)
            .order_by(EventLog.id.desc())
            .first()
        )
        last_id_before = before[0] if before else 0

        # 发布（不使用返回值，避免 detached instance）
        event_bus.publish("STOCK_OUT", payload)

        # 在 db_session 中查询刚插入的事件
        db_session.expire_all()
        ev = (
            db_session.query(EventLog)
            .filter(EventLog.id > last_id_before)
            .first()
        )
        assert ev is not None, "STOCK_OUT event not found after publish"
        return ev

    # ── 正常流程 ───────────────────────────────────────────

    def test_stock_out_deduces_ebay_inventory(
        self, db_session, event_bus, setup_listing, mock_ebay_client
    ):
        """STOCK_OUT 事件 → eBay 库存减少"""
        from modules.inventory_online.event_handlers import handle_stock_out

        event_bus.subscribe("STOCK_OUT", handle_stock_out)

        ev = self._stock_out(
            event_bus,
            db_session,
            sku="HANDLER-TEST-001",
            quantity=3,
            related_order="ORDER-STOCKOUT-001",
        )

        db_session.expire_all()
        updated = db_session.query(EbayListing).filter(
            EbayListing.sku == "HANDLER-TEST-001"
        ).first()

        assert updated.quantity_available == 7, (
            f"expected 7, got {updated.quantity_available}"
        )
        assert ev.status == EventStatus.DONE

    def test_stock_out_publishes_listing_updated_event(
        self, db_session, event_bus, setup_listing, mock_ebay_client
    ):
        """STOCK_OUT 处理成功 → 发布 LISTING_UPDATED 事件"""
        from modules.inventory_online.event_handlers import handle_stock_out

        event_bus.subscribe("STOCK_OUT", handle_stock_out)

        self._stock_out(
            event_bus,
            db_session,
            sku="HANDLER-TEST-001",
            quantity=2,
            related_order="ORDER-LISTING-UPD-001",
        )

        listing_updated = db_session.query(EventLog).filter(
            EventLog.event_type == "LISTING_UPDATED",
            EventLog.status == EventStatus.DONE,
        ).order_by(EventLog.created_at.desc()).first()

        assert listing_updated is not None, "LISTING_UPDATED event not published"
        assert listing_updated.payload and "HANDLER-TEST-001" in (
            listing_updated.payload.get("sku") or ""
        )

    # ── 防重复扣减 ─────────────────────────────────────────

    def test_duplicate_related_order_skipped(
        self, db_session, event_bus, setup_listing, mock_ebay_client
    ):
        """同 related_order 重复 STOCK_OUT → 第二次跳过"""
        from modules.inventory_online.event_handlers import handle_stock_out

        event_bus.subscribe("STOCK_OUT", handle_stock_out)
        order_id = "ORDER-DUP-TEST-001"

        # 第一次：qty 10 → 7
        self._stock_out(
            event_bus,
            db_session,
            sku="HANDLER-TEST-001",
            quantity=3,
            related_order=order_id,
        )
        db_session.expire_all()
        qty_after_first = db_session.query(EbayListing).filter(
            EbayListing.sku == "HANDLER-TEST-001"
        ).first().quantity_available

        # 第二次同订单（重复）：应跳过，qty 仍为 7
        self._stock_out(
            event_bus,
            db_session,
            sku="HANDLER-TEST-001",
            quantity=5,
            related_order=order_id,
        )
        db_session.expire_all()
        qty_after_second = db_session.query(EbayListing).filter(
            EbayListing.sku == "HANDLER-TEST-001"
        ).first().quantity_available

        assert qty_after_second == qty_after_first == 7, (
            f"duplicate should be skipped: first={qty_after_first}, second={qty_after_second}"
        )

    # ── 边界情况 ──────────────────────────────────────────

    def test_sku_without_listing_marked_done(
        self, db_session, event_bus, mock_ebay_client
    ):
        """SKU 无 eBay listing → handler 跳过，事件仍标记 DONE"""
        from modules.inventory_online.event_handlers import handle_stock_out

        event_bus.subscribe("STOCK_OUT", handle_stock_out)

        prod = Product(
            sku="NO-LISTING-SKU",
            title="No Listing Product",
            cost_price=Decimal("100.00"),
            cost_currency="JPY",
            status=ProductStatus.ACTIVE,
            supplier="Test",
        )
        db_session.add(prod)
        db_session.commit()

        ev = self._stock_out(
            event_bus,
            db_session,
            sku="NO-LISTING-SKU",
            quantity=1,
            related_order="ORDER-NO-LISTING",
        )

        assert ev.status == EventStatus.DONE

    def test_zero_quantity_skipped(
        self, db_session, event_bus, setup_listing, mock_ebay_client
    ):
        """quantity=0 → handler 跳过，库存不变"""
        from modules.inventory_online.event_handlers import handle_stock_out

        event_bus.subscribe("STOCK_OUT", handle_stock_out)

        ev = self._stock_out(
            event_bus,
            db_session,
            sku="HANDLER-TEST-001",
            quantity=0,
            related_order="ORDER-ZERO-QTY",
        )

        assert ev.status == EventStatus.DONE
        db_session.expire_all()
        listing = db_session.query(EbayListing).filter(
            EbayListing.sku == "HANDLER-TEST-001"
        ).first()
        assert listing.quantity_available == 10

    def test_ebay_api_failure_marks_event_failed(
        self, db_session, event_bus, setup_listing, mock_ebay_client
    ):
        """eBay API 调用失败 → 事件标记 FAILED"""
        from modules.inventory_online.event_handlers import handle_stock_out

        event_bus.subscribe("STOCK_OUT", handle_stock_out)

        # 让 mock client.put 抛出异常
        mock_ebay_client.put.side_effect = RuntimeError("API error")

        ev = self._stock_out(
            event_bus,
            db_session,
            sku="HANDLER-TEST-001",
            quantity=2,
            related_order="ORDER-API-FAIL",
        )

        assert ev.status == EventStatus.FAILED
        assert "API error" in (ev.error_message or "")
