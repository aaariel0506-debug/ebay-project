"""
tests/test_ebay_client.py

Day 28.5: EbayClient 多 base URL 路由测试
"""

from unittest.mock import MagicMock, patch

from core.ebay_api.client import EbayClient


class TestClientRouting:
    """client.py 多 base URL 路由测试"""

    def test_finances_api_routes_to_apiz_domain(self):
        """Finances API 调用走 apiz.ebay.com"""
        captured_urls = []

        def fake_request(method, url, **kwargs):
            captured_urls.append(url)
            resp = MagicMock()
            resp.status_code = 200
            resp.text = '{"transactions": []}'
            resp.json.return_value = {"transactions": []}
            return resp

        with patch("httpx.request", side_effect=fake_request):
            client = EbayClient()
            client.get("/sell/finances/v1/transaction", params={"orderId": "TEST-001"})

        assert len(captured_urls) == 1
        assert "apiz.ebay.com" in captured_urls[0], (
            f"Finances API 应走 apiz.ebay.com，实际 URL: {captured_urls[0]}"
        )
        assert "/sell/finances/v1/transaction" in captured_urls[0]

    def test_non_finances_api_routes_to_api_domain(self):
        """非 Finances API 调用走 api.ebay.com"""
        captured_urls = []

        def fake_request(method, url, **kwargs):
            captured_urls.append(url)
            resp = MagicMock()
            resp.status_code = 200
            resp.text = '{"orders": []}'
            resp.json.return_value = {"orders": []}
            return resp

        with patch("httpx.request", side_effect=fake_request):
            client = EbayClient()
            client.get("/sell/fulfillment/v1/order/TEST-001")

        assert len(captured_urls) == 1
        assert "api.ebay.com" in captured_urls[0], (
            f"Fulfillment API 应走 api.ebay.com，实际 URL: {captured_urls[0]}"
        )
        assert "apiz.ebay.com" not in captured_urls[0]

    def test_settings_has_ebay_finances_url_property(self):
        """settings.ebay_finances_url 在 production 和 sandbox 返回正确值"""
        from core.config.settings import Settings

        # Production
        s_prod = Settings(EBAY_ENV="production")
        assert s_prod.ebay_finances_url == "https://apiz.ebay.com"

        # Sandbox
        s_sand = Settings(EBAY_ENV="sandbox")
        assert s_sand.ebay_finances_url == "https://apiz.sandbox.ebay.com"
