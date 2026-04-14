"""tests/test_listing_service.py — Day 7 Listing Service 测试"""
from unittest.mock import MagicMock, patch

import pytest
from modules.listing.schemas import (
    InventoryItemResponse,
    ListingCreateRequest,
    ListingCreateResponse,
    OfferResponse,
)
from modules.listing.service import ListingCreateError, ListingService
from modules.listing.utils import (
    EBAY_CONDITIONS,
    EBAY_MARKETPLACE_IDS,
    build_inventory_availability,
    build_offers_pricing_summary,
    extract_listing_id_from_href,
    format_price,
    normalize_condition,
    validate_image_urls,
)


class TestListingSchemas:
    """Listing Request/Response Schema 测试"""

    def test_listing_create_request_valid(self):
        req = ListingCreateRequest(
            sku="SKU-TEST-001",
            title="Test Listing",
            condition="NEW",
            listing_price=19.99,
            quantity=10,
            currency="USD",
            marketplace_id="EBAY_US",
        )
        assert req.sku == "SKU-TEST-001"
        assert req.listing_price == 19.99
        assert req.quantity == 10

    def test_listing_create_request_defaults(self):
        req = ListingCreateRequest(
            sku="SKU-002",
            title="T",
            condition="GOOD",
            listing_price=9.99,
            quantity=0,
        )
        assert req.currency == "USD"
        assert req.marketplace_id == "EBAY_US"
        assert req.quantity == 0

    def test_listing_create_request_negative_price_fails(self):
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            ListingCreateRequest(
                sku="SKU-003",
                title="T",
                condition="NEW",
                listing_price=-5.0,
            )

    def test_inventory_item_response(self):
        resp = InventoryItemResponse(sku="SKU-001", status="created")
        assert resp.sku == "SKU-001"

    def test_offer_response(self):
        resp = OfferResponse(offer_id="offer-123", sku="SKU-001", status="created")
        assert resp.offer_id == "offer-123"

    def test_listing_create_response_success(self):
        resp = ListingCreateResponse(
            success=True,
            ebay_item_id="item-999",
            offer_id="offer-888",
            sku="SKU-001",
            status="ACTIVE",
        )
        assert resp.success is True
        assert resp.ebay_item_id == "item-999"


class TestListingUtils:
    """Listing 工具函数测试"""

    def test_normalize_condition_valid_eBay_standard(self):
        assert normalize_condition("NEW") == "NEW"
        assert normalize_condition("GOOD") == "GOOD"
        assert normalize_condition("VERY_GOOD") == "VERY_GOOD"

    def test_normalize_condition_friendly_input(self):
        assert normalize_condition("new") == "NEW"
        assert normalize_condition("good") == "GOOD"

    def test_normalize_condition_invalid(self):
        with pytest.raises(ValueError):
            normalize_condition("invalid_condition_xyz")

    def test_build_inventory_availability(self):
        avail = build_inventory_availability(50)
        assert avail["shipToLocationAvailability"]["quantity"] == 50

    def test_build_offers_pricing_summary(self):
        summary = build_offers_pricing_summary(19.99, "USD")
        assert summary["price"]["currency"] == "USD"
        assert summary["price"]["value"] == "19.99"

    def test_format_price(self):
        assert format_price(19.99) == "19.99"
        assert format_price(100.0) == "100.00"
        assert format_price(0.5) == "0.50"

    def test_extract_listing_id_from_href(self):
        href = "https://www.ebay.com/itm/284756123456"
        assert extract_listing_id_from_href(href) == "284756123456"
        assert extract_listing_id_from_href(None) is None
        assert extract_listing_id_from_href("") is None

    def test_validate_image_urls(self):
        urls = [
            "https://example.com/img1.jpg",
            "http://example.com/img2.png",
            "not-a-url",
            "https://example.com/img3.gif",
        ]
        valid = validate_image_urls(urls)
        assert len(valid) == 3
        assert "not-a-url" not in valid

    def test_ebay_conditions_defined(self):
        assert "NEW" in EBAY_CONDITIONS
        assert "GOOD" in EBAY_CONDITIONS

    def test_ebay_marketplace_ids(self):
        assert EBAY_MARKETPLACE_IDS["US"] == "EBAY_US"
        assert EBAY_MARKETPLACE_IDS["UK"] == "EBAY_GB"


class TestListingServiceUnit:
    """ListingService 单元测试（mock API 响应）"""

    def _make_mock_client(self):
        return MagicMock()

    def test_create_inventory_item_success(self):
        mock_client = self._make_mock_client()
        mock_client.put.return_value = {"sku": "SKU-001"}
        service = ListingService(client=mock_client)
        req = ListingCreateRequest(
            sku="SKU-001",
            title="T",
            condition="NEW",
            listing_price=10.0,
            quantity=5,
        )
        resp = service._create_inventory_item(req)
        assert resp.sku == "SKU-001"
        mock_client.put.assert_called_once()

    def test_create_offer_returns_offer_id(self):
        mock_client = self._make_mock_client()
        mock_client.post.return_value = {"offerId": "offer-abc-123"}
        service = ListingService(client=mock_client)
        req = ListingCreateRequest(
            sku="SKU-OFFER-001",
            title="T",
            condition="NEW",
            listing_price=15.0,
            quantity=5,
        )
        offer_id = service._create_offer(req)
        assert offer_id == "offer-abc-123"

    def test_create_offer_missing_offer_id_raises(self):
        mock_client = self._make_mock_client()
        mock_client.post.return_value = {}
        service = ListingService(client=mock_client)
        req = ListingCreateRequest(
            sku="SKU-ERR-001",
            title="T",
            condition="NEW",
            listing_price=10.0,
            quantity=5,
        )
        with pytest.raises(ListingCreateError) as exc_info:
            service._create_offer(req)
        assert "createOffer" in str(exc_info.value)

    def test_publish_offer_returns_listing_id(self):
        mock_client = self._make_mock_client()
        mock_client.post.return_value = {"listingId": "284756789012"}
        service = ListingService(client=mock_client)
        listing_id = service._publish_offer("offer-xyz")
        assert listing_id == "284756789012"

    def test_publish_offer_extracts_from_href(self):
        mock_client = self._make_mock_client()
        mock_client.post.return_value = {
            "listingId": None,
            "listingIdHref": "https://www.ebay.com/itm/284756789012",
        }
        service = ListingService(client=mock_client)
        listing_id = service._publish_offer("offer-xyz")
        assert listing_id == "284756789012"

    def test_full_flow_step1_failure_returns_error(self):
        from core.ebay_api.exceptions import EbayApiError
        mock_client = self._make_mock_client()
        mock_client.put.side_effect = EbayApiError(
            "Invalid SKU",
            status_code=400,
        )
        service = ListingService(client=mock_client)
        req = ListingCreateRequest(
            sku="SKU-FAIL-001",
            title="T",
            condition="NEW",
            listing_price=10.0,
            quantity=5,
        )
        resp = service.create_single_listing(req)
        assert resp.success is False
        assert any("inventory_item" in e for e in resp.errors)


class TestListingServiceIntegration:
    """ListingService 集成测试（实际 DB 操作，需要 mock API）"""

    def _make_mock_client(self):
        mock = MagicMock()
        mock.put.return_value = {"sku": "MOCK-SKU"}
        # First POST = createOffer, Second POST = publishOffer
        mock.post.side_effect = [
            {"offerId": "mock-offer-123"},  # createOffer
            {"listingId": "mock-item-999"},  # publishOffer
        ]
        mock.delete.return_value = {}
        return mock

    def test_create_single_listing_full_flow(self):
        """模拟完整 3 步流程 + DB 写入（mock API + mock DB session）"""
        mock_client = self._make_mock_client()
        service = ListingService(client=mock_client)

        req = ListingCreateRequest(
            sku="SKU-FLOW-001",
            title="Flow Test Product",
            condition="NEW",
            listing_price=29.99,
            quantity=100,
        )

        mock_event_bus = MagicMock()

        with patch("modules.listing.service.get_session") as mock_session:
            mock_s = MagicMock()
            mock_session.return_value.__enter__ = MagicMock(return_value=mock_s)
            mock_session.return_value.__exit__ = MagicMock(return_value=False)
            mock_s.query.return_value.filter_by.return_value.first.return_value = None

            # Inject mock event bus directly (bypass __init__)
            service._event_bus = mock_event_bus

            resp = service.create_single_listing(req)

        assert resp.success is True
        assert resp.offer_id == "mock-offer-123"
        mock_client.put.assert_called_once()
        assert mock_client.post.call_count == 2  # createOffer + publishOffer
        mock_event_bus.publish.assert_called_once()
        call_args = mock_event_bus.publish.call_args
        assert call_args[0][0] == "LISTING_CREATED"
