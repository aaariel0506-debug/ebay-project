"""Tests for inventory online sync service (Day 13)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from modules.inventory_online.sync_service import (
    PAGE_SIZE,
    SyncResult,
    SyncService,
)

# ── Fixtures ────────────────────────────────────────────────────────────────

@pytest.fixture
def sync_service() -> SyncService:
    return SyncService(client=MagicMock())


# ── Test SyncResult ────────────────────────────────────────────────────────

class TestSyncResult:
    def test_summary(self):
        r = SyncResult(
            total_on_ebay=100,
            new_count=10,
            updated_count=80,
            ended_count=5,
            error_count=2,
        )
        s = r.summary()
        assert "100" in s
        assert "新增 10" in s
        assert "更新 80" in s
        assert "下架 5" in s
        assert "错误 2" in s


# ── Test _fetch_all_inventory_items ───────────────────────────────────────

class TestFetchAll:
    def test_empty_response(self, sync_service: SyncService):
        sync_service.client.get = MagicMock(return_value={"inventoryItems": []})
        items = sync_service._fetch_all_inventory_items()
        assert items == []

    def test_single_page(self, sync_service: SyncService):
        mock_items = [
            {"sku": "SKU001", "availability": {"shipToLocationAvailability": {"availableQuantity": 5}}},
            {"sku": "SKU002", "availability": {"shipToLocationAvailability": {"availableQuantity": 3}}},
        ]
        sync_service.client.get = MagicMock(return_value={
            "inventoryItems": mock_items,
            "total": 2,
        })
        items = sync_service._fetch_all_inventory_items()
        assert len(items) == 2
        assert items[0]["sku"] == "SKU001"

    def test_multiple_pages(self, sync_service: SyncService):
        page1 = [{"sku": f"SKU{i:03d}"} for i in range(1, 101)]
        page2 = [{"sku": f"SKU{i:03d}"} for i in range(101, 151)]

        def mock_get(path, params=None, **kwargs):
            offset = params.get("offset", 0) if params else 0
            if offset == 0:
                return {"inventoryItems": page1, "total": 150}
            elif offset == 100:
                return {"inventoryItems": page2, "total": 150}
            return {"inventoryItems": [], "total": 150}

        sync_service.client.get = MagicMock(side_effect=mock_get)
        items = sync_service._fetch_all_inventory_items()
        assert len(items) == 150
        assert items[0]["sku"] == "SKU001"
        assert items[149]["sku"] == "SKU150"

    def test_page_size_constant(self):
        assert PAGE_SIZE == 100


# ── Test full_sync flow ───────────────────────────────────────────────────

class TestFullSync:
    def test_full_sync_new_items(self, sync_service: SyncService):
        mock_items = [
            {
                "sku": "SYNC-SKU-001",
                "availability": {"shipToLocationAvailability": {"availableQuantity": 10}},
                "pricingSummaries": [{"price": {"value": "150.00"}}],
            },
        ]
        sync_service.client.get = MagicMock(return_value={
            "inventoryItems": mock_items, "total": 1
        })

        with patch("core.database.connection.get_session") as mock_sess:
            sess = MagicMock()
            mock_sess.return_value.__enter__ = MagicMock(return_value=sess)
            mock_sess.return_value.__exit__ = MagicMock(return_value=False)
            sess.query.return_value.filter.return_value.first.return_value = None
            sess.query.return_value.filter.return_value.all.return_value = []

            result = sync_service.full_sync()

        assert result.total_on_ebay == 1
        assert result.new_count == 1
        assert result.updated_count == 0
        assert result.ended_count == 0
        assert result.error_count == 0

    def test_full_sync_updates_existing(self, sync_service: SyncService):
        mock_items = [
            {
                "sku": "SYNC-SKU-002",
                "availability": {"shipToLocationAvailability": {"availableQuantity": 20}},
                "pricingSummaries": [{"price": {"value": "250.00"}}],
            },
        ]
        sync_service.client.get = MagicMock(return_value={
            "inventoryItems": mock_items, "total": 1
        })

        with patch("core.database.connection.get_session") as mock_sess:
            sess = MagicMock()
            mock_sess.return_value.__enter__ = MagicMock(return_value=sess)
            mock_sess.return_value.__exit__ = MagicMock(return_value=False)

            # Existing record found
            existing = MagicMock()
            sess.query.return_value.filter.return_value.first.return_value = existing
            sess.query.return_value.filter.return_value.all.return_value = []

            result = sync_service.full_sync()

        assert result.new_count == 0
        assert result.updated_count == 1

    def test_full_sync_marks_ended(self, sync_service: SyncService):
        mock_items = []  # eBay has nothing
        sync_service.client.get = MagicMock(return_value={
            "inventoryItems": mock_items, "total": 0
        })

        with patch("core.database.connection.get_session") as mock_sess:
            sess = MagicMock()
            mock_sess.return_value.__enter__ = MagicMock(return_value=sess)
            mock_sess.return_value.__exit__ = MagicMock(return_value=False)

            # One local listing that is no longer on eBay
            local_listing = MagicMock()
            local_listing.sku = "OLD-SKU-001"
            sess.query.return_value.filter.return_value.all.return_value = [local_listing]

            result = sync_service.full_sync()

        assert result.ended_count == 1
        assert result.total_on_ebay == 0

    def test_full_sync_handles_api_error(self, sync_service: SyncService):
        sync_service.client.get = MagicMock(side_effect=Exception("API error 500"))

        with patch("core.database.connection.get_session") as mock_sess:
            sess = MagicMock()
            mock_sess.return_value.__enter__ = MagicMock(return_value=sess)
            mock_sess.return_value.__exit__ = MagicMock(return_value=False)
            sess.query.return_value.filter.return_value.all.return_value = []

            result = sync_service.full_sync()

        assert result.error_count == 1
        assert "API error 500" in result.errors[0]


# ── Test _upsert_listing ─────────────────────────────────────────────────

class TestUpsert:
    def test_upsert_creates_new(self, sync_service: SyncService):
        item = {
            "sku": "UPSERT-NEW",
            "availability": {"shipToLocationAvailability": {"availableQuantity": 7}},
            "pricingSummaries": [{"price": {"value": "88.00"}}],
        }

        with patch("core.database.connection.get_session") as mock_sess:
            sess = MagicMock()
            mock_sess.return_value.__enter__ = MagicMock(return_value=sess)
            mock_sess.return_value.__exit__ = MagicMock(return_value=False)
            sess.query.return_value.filter.return_value.first.return_value = None

            is_new = sync_service._upsert_listing(item)

        assert is_new is True
        sess.add.assert_called_once()
        sess.commit.assert_called_once()

    def test_upsert_updates_existing(self, sync_service: SyncService):
        item = {
            "sku": "UPSERT-EXISTING",
            "availability": {"shipToLocationAvailability": {"availableQuantity": 15}},
            "pricingSummaries": [{"price": {"value": "99.00"}}],
        }

        with patch("core.database.connection.get_session") as mock_sess:
            sess = MagicMock()
            mock_sess.return_value.__enter__ = MagicMock(return_value=sess)
            mock_sess.return_value.__exit__ = MagicMock(return_value=False)
            existing = MagicMock()
            sess.query.return_value.filter.return_value.first.return_value = existing

            is_new = sync_service._upsert_listing(item)

        assert is_new is False
        assert existing.quantity_available == 15
        assert existing.listing_price == 99.0
        sess.commit.assert_called_once()


# ── Test _mark_ended ───────────────────────────────────────────────────────

class TestMarkEnded:
    def test_mark_ended_skips_active(self, sync_service: SyncService):
        with patch("core.database.connection.get_session") as mock_sess:
            sess = MagicMock()
            mock_sess.return_value.__enter__ = MagicMock(return_value=sess)
            mock_sess.return_value.__exit__ = MagicMock(return_value=False)

            # 3 local listings, all still on eBay
            local = MagicMock()
            local.sku = "STILL-ACTIVE"
            sess.query.return_value.filter.return_value.all.return_value = [local]

            ended = sync_service._mark_ended_listings({"STILL-ACTIVE"})

        assert ended == 0

    def test_mark_ended_counts_correctly(self, sync_service: SyncService):
        with patch("core.database.connection.get_session") as mock_sess:
            sess = MagicMock()
            mock_sess.return_value.__enter__ = MagicMock(return_value=sess)
            mock_sess.return_value.__exit__ = MagicMock(return_value=False)

            l1, l2 = MagicMock(), MagicMock()
            l1.sku = "GONE-1"
            l2.sku = "GONE-2"
            sess.query.return_value.filter.return_value.all.return_value = [l1, l2]

            ended = sync_service._mark_ended_listings({"STILL-THERE"})

        assert ended == 2
        assert l1.status.name == "ENDED"
        assert l2.status.name == "ENDED"
