"""
tests/test_listing_creator.py — Listing 创建器测试
使用 mock 隔离 eBay API
"""
import pytest
import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).parent.parent))

from listing_creator import ListingResult


class TestListingResult:
    """ListingResult 数据类测试"""

    def test_default_is_failure(self):
        result = ListingResult(sku="TEST-001")
        assert result.success is False
        assert result.offer_id == ""
        assert result.listing_id == ""

    def test_success_status_text(self):
        result = ListingResult(sku="TEST-001", success=True)
        assert result.status_text == "SUCCESS"

    def test_failure_status_text(self):
        result = ListingResult(sku="TEST-001", success=False, step_failed="create_inventory")
        assert "FAILED" in result.status_text
        assert "create_inventory" in result.status_text

    def test_stores_error_message(self):
        result = ListingResult(sku="TEST-001", error="API timeout")
        assert result.error == "API timeout"


class TestListingCreator:
    """ListingCreator 测试（mock HTTP）"""

    @pytest.fixture
    def mock_client(self, tmp_path):
        config = {
            "environment": "sandbox",
            "sandbox": {"api_base": "https://api.sandbox.ebay.com", "web_base": ""},
            "marketplace": {"marketplace_id": "EBAY_US", "currency": "USD", "locale": "en_US"},
            "oauth": {"app_id": "test", "cert_id": "test", "user_token": "tok", "refresh_token": "ref"},
            "business_policies": {"payment_policy_id": "p1", "fulfillment_policy_id": "f1", "return_policy_id": "r1"},
            "listing_defaults": {"auto_publish": False, "condition": "NEW", "condition_id": "1000"},
            "merchant_location_key": "JP",
        }
        config_path = tmp_path / "config.json"
        config_path.write_text(json.dumps(config))

        from ebay_client import EbayClient
        client = EbayClient(config_path=config_path)
        return client

    def test_creator_initializes(self, mock_client):
        from listing_creator import ListingCreator
        creator = ListingCreator(mock_client)
        assert creator.client is mock_client

    @patch("requests.request")
    def test_create_listing_calls_api(self, mock_request, mock_client):
        """验证 create_listing 调用 eBay API"""
        from listing_creator import ListingCreator

        # Mock: first call = put inventory item (204), second = post offer (201)
        mock_response_inventory = MagicMock()
        mock_response_inventory.status_code = 204
        mock_response_inventory.text = ""
        mock_response_inventory.headers = {}

        mock_response_offer = MagicMock()
        mock_response_offer.status_code = 201
        mock_response_offer.text = json.dumps({"offerId": "OFFER-123"})
        mock_response_offer.json.return_value = {"offerId": "OFFER-123"}
        mock_response_offer.headers = {}

        mock_request.side_effect = [mock_response_inventory, mock_response_offer]

        creator = ListingCreator(mock_client)
        item = {
            "sku": "TEST-SKU",
            "title": "Test Product for Unit Testing",
            "description": "A test product description that is long enough for validation.",
            "category_id": "172008",
            "price": 29.99,
            "quantity": 3,
            "image_urls": "https://example.com/img.jpg",
            "condition": "NEW",
        }

        result = creator.create_listing(item, auto_publish=False)
        assert result.sku == "TEST-SKU"
        # At least one HTTP request was made
        assert mock_request.call_count >= 1
