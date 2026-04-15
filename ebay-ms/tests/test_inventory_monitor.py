"""Tests for inventory online monitor (Day 14)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from modules.inventory_online.monitor import (
    InventoryMonitor,
    StockStatus,
)

# ── Helpers ────────────────────────────────────────────────────────────────

def _mock_listing(sku, qty, price, status_name="ACTIVE"):
    m = MagicMock()
    m.sku = sku
    m.ebay_item_id = "ITEM001"
    m.title = "Test"
    m.quantity_available = qty
    m.listing_price = price
    m.variants = None
    m.status.name = status_name
    return m


# ── Fixtures ────────────────────────────────────────────────────────────────

@pytest.fixture
def monitor() -> InventoryMonitor:
    return InventoryMonitor(client=MagicMock())


# ── Test StockStatus ───────────────────────────────────────────────────────

class TestStockStatus:
    def test_out_of_stock(self):
        s = StockStatus(sku="X", ebay_item_id="I1", title="T", quantity=0, listing_price=100.0, status="OUT_OF_STOCK")
        assert s.is_out_of_stock is True
        assert s.is_low_stock is False

    def test_low_stock(self):
        s = StockStatus(sku="X", ebay_item_id="I1", title="T", quantity=2, listing_price=100.0, status="LOW_STOCK")
        assert s.is_out_of_stock is False
        assert s.is_low_stock is True

    def test_normal(self):
        s = StockStatus(sku="X", ebay_item_id="I1", title="T", quantity=10, listing_price=100.0, status="NORMAL")
        assert s.is_out_of_stock is False
        assert s.is_low_stock is False


# ── Test _to_stock_status ─────────────────────────────────────────────────

class TestToStockStatus:
    def test_normal(self, monitor):
        s = monitor._to_stock_status(_mock_listing("SKU-NORMAL", 10, 150.0))
        assert s.sku == "SKU-NORMAL"
        assert s.status == "NORMAL"

    def test_out_of_stock(self, monitor):
        s = monitor._to_stock_status(_mock_listing("SKU-OOS", 0, 99.0))
        assert s.status == "OUT_OF_STOCK"

    def test_low_stock(self, monitor):
        s = monitor._to_stock_status(_mock_listing("SKU-LOW", 2, 50.0))
        assert s.status == "LOW_STOCK"

    def test_ended(self, monitor):
        s = monitor._to_stock_status(_mock_listing("SKU-ENDED", 5, 80.0, "ENDED"))
        assert s.status == "ENDED"


# ── Test list_out_of_stock ─────────────────────────────────────────────────

class TestListOutOfStock:
    def test_returns_only_oos(self, monitor):
        mock_listing = _mock_listing("OOS-SKU", 0, 100.0)
        with patch("core.database.connection.get_session") as mock_sess:
            sess = MagicMock()
            mock_sess.return_value.__enter__ = MagicMock(return_value=sess)
            mock_sess.return_value.__exit__ = MagicMock(return_value=False)
            sess.query.return_value.filter.return_value.all.return_value = [mock_listing]
            results = monitor.list_out_of_stock()
        assert len(results) == 1
        assert results[0].sku == "OOS-SKU"
        assert results[0].is_out_of_stock is True

    def test_empty(self, monitor):
        with patch("core.database.connection.get_session") as mock_sess:
            sess = MagicMock()
            mock_sess.return_value.__enter__ = MagicMock(return_value=sess)
            mock_sess.return_value.__exit__ = MagicMock(return_value=False)
            sess.query.return_value.filter.return_value.all.return_value = []
            results = monitor.list_out_of_stock()
        assert results == []


# ── Test list_low_stock ────────────────────────────────────────────────────

class TestListLowStock:
    def test_returns_low(self, monitor):
        mock_listing = _mock_listing("LOW-SKU", 1, 50.0)
        with patch("core.database.connection.get_session") as mock_sess:
            sess = MagicMock()
            mock_sess.return_value.__enter__ = MagicMock(return_value=sess)
            mock_sess.return_value.__exit__ = MagicMock(return_value=False)
            sess.query.return_value.filter.return_value.all.return_value = [mock_listing]
            results = monitor.list_low_stock()
        assert len(results) == 1
        assert results[0].is_low_stock is True

    def test_custom_threshold(self, monitor):
        mock_listing = _mock_listing("MED-SKU", 5, 60.0)
        with patch("core.database.connection.get_session") as mock_sess:
            sess = MagicMock()
            mock_sess.return_value.__enter__ = MagicMock(return_value=sess)
            mock_sess.return_value.__exit__ = MagicMock(return_value=False)
            sess.query.return_value.filter.return_value.all.return_value = [mock_listing]
            results = monitor.list_low_stock(threshold=5)
        assert len(results) == 1


# ── Test get_stock_summary ─────────────────────────────────────────────────

class TestGetStockSummary:
    def test_counts(self, monitor):
        with patch("core.database.connection.get_session") as mock_sess:
            sess = MagicMock()
            mock_sess.return_value.__enter__ = MagicMock(return_value=sess)
            mock_sess.return_value.__exit__ = MagicMock(return_value=False)
            sess.query.return_value.filter.return_value.count.side_effect = [100, 5, 10, 3]
            summary = monitor.get_stock_summary()
        assert summary["total_active"] == 100
        assert summary["out_of_stock"] == 5
        assert summary["low_stock"] == 10
        assert summary["ended"] == 3


# ── Test _publish_stock_alerts ─────────────────────────────────────────────

class TestPublishAlerts:
    def test_oos_alert(self, monitor):
        oos_item = StockStatus(sku="OOS-001", ebay_item_id="I1", title="OOS",
                               quantity=0, listing_price=100.0, status="OUT_OF_STOCK")
        with patch("core.events.bus.EventBus") as MockBus:
            mock_bus = MagicMock()
            MockBus.return_value = mock_bus
            monitor._publish_stock_alerts(out_of_stock=[oos_item], low_stock=[])
        mock_bus.publish.assert_called_once()
        call = mock_bus.publish.call_args
        assert call.kwargs["event_type"] == "STOCK_ALERT"
        assert call.kwargs["payload"]["alert_type"] == "OUT_OF_STOCK"
        assert "OOS-001" in call.kwargs["payload"]["skus"]

    def test_low_stock_alert(self, monitor):
        low_item = StockStatus(sku="LOW-001", ebay_item_id="I2", title="Low",
                               quantity=1, listing_price=50.0, status="LOW_STOCK")
        with patch("core.events.bus.EventBus") as MockBus:
            mock_bus = MagicMock()
            MockBus.return_value = mock_bus
            monitor._publish_stock_alerts(out_of_stock=[], low_stock=[low_item])
        call = mock_bus.publish.call_args
        assert call.kwargs["payload"]["alert_type"] == "LOW_STOCK"
        assert "LOW-001" in call.kwargs["payload"]["skus"]

    def test_no_alert_when_empty(self, monitor):
        with patch("core.events.bus.EventBus") as MockBus:
            mock_bus = MagicMock()
            MockBus.return_value = mock_bus
            monitor._publish_stock_alerts(out_of_stock=[], low_stock=[])
        mock_bus.publish.assert_not_called()


# ── Test list_all ──────────────────────────────────────────────────────────

class TestListAll:
    def test_pagination(self, monitor):
        mock_listing = _mock_listing("PAG-SKU", 8, 120.0)
        with patch("core.database.connection.get_session") as mock_sess:
            sess = MagicMock()
            mock_sess.return_value.__enter__ = MagicMock(return_value=sess)
            mock_sess.return_value.__exit__ = MagicMock(return_value=False)
            sess.query.return_value.order_by.return_value.offset.return_value.limit.return_value.all.return_value = [mock_listing]
            results = monitor.list_all(limit=20, offset=10)
        assert len(results) == 1
        assert results[0].sku == "PAG-SKU"
