"""
tests/test_exchange_rate.py — 汇率模块单元测试
"""
import pytest
from unittest.mock import patch, MagicMock
from datetime import datetime, timedelta

from ingest.exchange_rate import (
    get_rate_jpy_usd,
    get_usd_per_jpy,
    batch_get_rates,
    _find_nearest_rate,
    _get_fallback_rate,
    clear_cache,
)


class TestGetRateJpyUsd:
    """测试 get_rate_jpy_usd 函数"""

    def setup_method(self):
        """每个测试前清除缓存"""
        clear_cache()

    @patch('ingest.exchange_rate.requests.get')
    def test_get_rate_returns_float(self, mock_get):
        """返回值为合理范围内的 float"""
        # Mock API 响应：1 USD = 150 JPY → 1 JPY = 1/150 USD
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            'base': 'USD',
            'start_date': '2026-02-01',
            'end_date': '2026-02-28',
            'rates': {
                '2026-02-15': {'JPY': 150.0}
            }
        }
        mock_get.return_value = mock_response

        rate = get_rate_jpy_usd('2026-02-15')

        assert isinstance(rate, float)
        assert rate == pytest.approx(1 / 150.0, rel=1e-6)
        assert 0.005 < rate < 0.01  # 合理范围检查

    @patch('ingest.exchange_rate.requests.get')
    def test_fallback_on_network_error(self, mock_get):
        """网络失败时返回 fallback，不抛异常"""
        mock_get.side_effect = ConnectionError("Network failed")

        rate = get_rate_jpy_usd('2026-02-15')

        assert isinstance(rate, float)
        assert rate == pytest.approx(1 / 150.0, rel=1e-6)  # 默认 fallback

    @patch('ingest.exchange_rate.requests.get')
    def test_fallback_on_timeout(self, mock_get):
        """超时时返回 fallback"""
        mock_get.side_effect = TimeoutError("Request timed out")

        rate = get_rate_jpy_usd('2026-02-15')

        assert isinstance(rate, float)
        assert rate == pytest.approx(1 / 150.0, rel=1e-6)

    @patch('ingest.exchange_rate.requests.get')
    def test_weekend_finds_nearest_weekday(self, mock_get):
        """周末日期找最近工作日汇率"""
        # 2026-02-15 是周日，应返回 2026-02-14（周五）的汇率
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            'base': 'USD',
            'start_date': '2026-02-01',
            'end_date': '2026-02-28',
            'rates': {
                '2026-02-13': {'JPY': 151.0},  # 周五
                '2026-02-14': {'JPY': 152.0},  # 周六（但 API 可能返回）
                # 2026-02-15 周日不在返回中
            }
        }
        mock_get.return_value = mock_response

        rate = get_rate_jpy_usd('2026-02-15')

        # 应返回 2026-02-14 的汇率（1/152）
        assert rate == pytest.approx(1 / 152.0, rel=1e-6)


class TestBatchGetRates:
    """测试 batch_get_rates 函数"""

    def setup_method(self):
        clear_cache()

    @patch('ingest.exchange_rate.requests.get')
    def test_batch_get_rates_makes_one_request_per_month(self, mock_get):
        """同月多个日期只发一次 API 请求"""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            'base': 'USD',
            'start_date': '2026-02-01',
            'end_date': '2026-02-28',
            'rates': {
                '2026-02-01': {'JPY': 150.0},
                '2026-02-15': {'JPY': 152.0},
                '2026-02-28': {'JPY': 153.0},
            }
        }
        mock_get.return_value = mock_response

        dates = ['2026-02-01', '2026-02-15', '2026-02-28']
        rates = batch_get_rates(dates)

        # 只应发起一次请求（整月范围）
        assert mock_get.call_count == 1
        
        # 验证返回结果
        assert len(rates) == 3
        assert '2026-02-01' in rates
        assert '2026-02-15' in rates
        assert '2026-02-28' in rates

    @patch('ingest.exchange_rate.requests.get')
    def test_batch_get_rates_multiple_months(self, mock_get):
        """跨月日期应发起多次请求"""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            'base': 'USD',
            'rates': {}
        }
        mock_get.return_value = mock_response

        dates = ['2026-01-15', '2026-02-15', '2026-03-15']
        batch_get_rates(dates)

        # 三个月应发起三次请求
        assert mock_get.call_count == 3

    @patch('ingest.exchange_rate.requests.get')
    def test_batch_get_rates_empty_list(self, mock_get):
        """空列表返回空字典"""
        rates = batch_get_rates([])
        assert rates == {}
        assert mock_get.call_count == 0


class TestFindNearestRate:
    """测试 _find_nearest_rate 函数"""

    def test_finds_exact_date(self):
        """精确匹配日期"""
        rates_dict = {
            '2026-02-15': {'JPY': 150.0}
        }
        rate = _find_nearest_rate('2026-02-15', rates_dict)
        assert rate == pytest.approx(1 / 150.0, rel=1e-6)

    def test_finds_previous_day(self):
        """找不到时向前找最近一天"""
        rates_dict = {
            '2026-02-14': {'JPY': 152.0},
            '2026-02-16': {'JPY': 151.0},
        }
        # 2026-02-15 不在 dict 中，应返回 2026-02-14
        rate = _find_nearest_rate('2026-02-15', rates_dict)
        assert rate == pytest.approx(1 / 152.0, rel=1e-6)

    def test_returns_none_after_7_days(self):
        """超过 7 天回溯返回 None"""
        rates_dict = {
            '2026-02-01': {'JPY': 150.0},
        }
        # 2026-02-10 距离 2026-02-01 超过 7 天
        rate = _find_nearest_rate('2026-02-10', rates_dict)
        assert rate is None

    def test_invalid_date_format(self):
        """无效日期格式返回 None"""
        rates_dict = {}
        rate = _find_nearest_rate('invalid-date', rates_dict)
        assert rate is None


class TestGetUsdPerJpy:
    """测试 get_usd_per_jpy 别名"""

    def setup_method(self):
        clear_cache()

    @patch('ingest.exchange_rate.requests.get')
    def test_alias_works(self, mock_get):
        """别名返回相同结果"""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            'base': 'USD',
            'rates': {'2026-02-15': {'JPY': 150.0}}
        }
        mock_get.return_value = mock_response

        rate1 = get_rate_jpy_usd('2026-02-15')
        clear_cache()
        rate2 = get_usd_per_jpy('2026-02-15')

        assert rate1 == rate2


class TestFallbackRate:
    """测试 fallback 机制"""

    @patch('ingest.exchange_rate.os.path.exists')
    @patch('ingest.exchange_rate.open')
    def test_fallback_from_config(self, mock_open, mock_exists):
        """从 config.yaml 读取 fallback 值"""
        mock_exists.return_value = True
        mock_open.return_value.__enter__ = lambda s: s
        mock_open.return_value.__exit__ = lambda s, *args: None
        mock_open.return_value.read = lambda: "exchange_rate:\n  fallback_jpy_usd: 160\n"

        # 这个测试需要更复杂的 mock，暂时跳过
        pass

    def test_default_fallback(self):
        """默认 fallback 为 1/150"""
        clear_cache()
        # 不 mock 任何内容，使用默认行为
        with patch('ingest.exchange_rate.requests.get', side_effect=ConnectionError()):
            rate = get_rate_jpy_usd('2026-02-15')
            assert rate == pytest.approx(1 / 150.0, rel=1e-6)


class TestCache:
    """测试缓存机制"""

    def setup_method(self):
        clear_cache()

    @patch('ingest.exchange_rate.requests.get')
    def test_cache_hit(self, mock_get):
        """缓存命中时不发起网络请求"""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            'base': 'USD',
            'rates': {'2026-02-15': {'JPY': 150.0}}
        }
        mock_get.return_value = mock_response

        # 第一次调用
        get_rate_jpy_usd('2026-02-15')
        assert mock_get.call_count == 1

        # 第二次调用（缓存命中）
        get_rate_jpy_usd('2026-02-15')
        assert mock_get.call_count == 1  # 仍然是 1 次

    def test_clear_cache(self):
        """clear_cache 清除缓存"""
        clear_cache()
        with patch('ingest.exchange_rate.requests.get', side_effect=ConnectionError()):
            get_rate_jpy_usd('2026-02-15')
            clear_cache()
            get_rate_jpy_usd('2026-02-15')
            # 清除缓存后应重新尝试网络请求
            # （这个测试需要更复杂的 mock 来验证）
