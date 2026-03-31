"""
tests/test_ebay_client.py — eBay API 客户端测试
使用 mock 隔离，不调用真实 API
"""
import json
import pytest
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

sys.path.insert(0, str(Path(__file__).parent.parent))


@pytest.fixture
def sample_config(tmp_path):
    """创建测试用配置文件"""
    config = {
        "environment": "sandbox",
        "sandbox": {
            "api_base": "https://api.sandbox.ebay.com",
            "web_base": "https://auth.sandbox.ebay.com",
        },
        "production": {
            "api_base": "https://api.ebay.com",
            "web_base": "https://auth.ebay.com",
        },
        "marketplace": {
            "marketplace_id": "EBAY_US",
            "currency": "USD",
            "locale": "en_US",
        },
        "oauth": {
            "app_id": "test-app-id",
            "cert_id": "test-cert-id",
            "user_token": "test-user-token",
            "refresh_token": "test-refresh-token",
        },
        "business_policies": {
            "payment_policy_id": "pay-001",
            "fulfillment_policy_id": "ful-001",
            "return_policy_id": "ret-001",
        },
        "listing_defaults": {
            "auto_publish": False,
            "condition": "NEW",
            "condition_id": "1000",
        },
        "merchant_location_key": "JP_WAREHOUSE",
    }
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps(config))
    return config_path


class TestEbayClientInit:
    """客户端初始化测试"""

    def test_loads_sandbox_config(self, sample_config):
        from ebay_client import EbayClient
        client = EbayClient(config_path=sample_config)
        assert client.api_base == "https://api.sandbox.ebay.com"
        assert client.marketplace_id == "EBAY_US"

    def test_loads_business_policies(self, sample_config):
        from ebay_client import EbayClient
        client = EbayClient(config_path=sample_config)
        assert client.payment_policy_id == "pay-001"
        assert client.fulfillment_policy_id == "ful-001"
        assert client.return_policy_id == "ret-001"

    def test_loads_listing_defaults(self, sample_config):
        from ebay_client import EbayClient
        client = EbayClient(config_path=sample_config)
        assert client.auto_publish is False
        assert client.default_condition == "NEW"
        assert client.merchant_location_key == "JP_WAREHOUSE"

    def test_missing_config_raises(self, tmp_path):
        from ebay_client import EbayClient
        with pytest.raises(FileNotFoundError):
            EbayClient(config_path=tmp_path / "nonexistent.json")

    def test_save_config_writes_file(self, sample_config):
        from ebay_client import EbayClient
        client = EbayClient(config_path=sample_config)
        client.config["test_key"] = "test_value"
        client.save_config()

        with open(sample_config) as f:
            saved = json.load(f)
        assert saved["test_key"] == "test_value"
