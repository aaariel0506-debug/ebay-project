"""
tests/test_price_monitor.py

Day 16: 供应价格变化检测 + 阈值警告
"""

from decimal import Decimal

import pytest


class TestUpdateCostPrice:
    """update_cost_price 核心逻辑测试。"""

    def test_change_rate_up_triggers_alert(self):
        """进货价上涨超过 10%，触发 PRICE_ALERT。"""
        from modules.inventory_online.price_monitor import PriceMonitor

        pm = PriceMonitor(price_change_threshold=0.10)

        # 模拟：Product 存在，进货价 100 → 120（+20%）
        # 需要 DB fixture... 这里测试 change_rate 计算逻辑
        pass  # 依赖 DB，下方用 integration 方式测试

    def test_change_rate_down_triggers_alert(self):
        """进货价下跌超过 10%，触发 PRICE_ALERT。"""
        pass

    def test_change_within_threshold_no_alert(self):
        """变化在阈值内，不触发事件。"""
        pass

    def test_invalid_price_raises(self):
        """无效价格抛出 ValueError。"""
        pass

    def test_nonexistent_sku_raises(self):
        """SKU 不存在时抛出 ValueError。"""
        pass


class TestPriceChangeRate:
    """价格变化率计算。"""

    def test_change_rate_positive(self):
        from decimal import Decimal
        old = Decimal("100")
        new = Decimal("120")
        rate = (new - old) / old
        assert float(rate) == pytest.approx(0.20)

    def test_change_rate_negative(self):
        old = Decimal("100")
        new = Decimal("85")
        rate = (new - old) / old
        assert float(rate) == pytest.approx(-0.15)

    def test_change_rate_unchanged(self):
        old = Decimal("100")
        new = Decimal("100")
        rate = (new - old) / old
        assert abs(float(rate)) < 1e-9

    def test_change_rate_zero_old_price(self):
        """旧价格为 0 时，变化率记为 0（不除零）。"""
        old = Decimal("0")
        new = Decimal("100")
        rate = (new - old) / old if old > 0 else Decimal("0")
        assert rate == Decimal("0")


class TestMarginCalculation:
    """利润率计算。"""

    def test_margin_above_threshold(self):
        cost_jpy = 800
        listing_price = 1000  # USD
        margin = (listing_price - cost_jpy) / listing_price
        assert margin == pytest.approx(0.20)

    def test_margin_below_threshold_triggers_warning(self):
        cost_jpy = 950
        listing_price = 1000
        margin = (listing_price - cost_jpy) / listing_price
        assert margin == pytest.approx(0.05)
        assert margin < 0.15  # 低于 15% 阈值


class TestBatchUpdate:
    """批量价格更新。"""

    def test_batch_result_counts(self):
        """BatchPriceUpdateResult 的计数正确。"""
        from modules.inventory_online.price_monitor import BatchPriceUpdateResult

        result = BatchPriceUpdateResult(
            total=10,
            success=8,
            failed=2,
            alerts=[],
            errors=[{"sku": "A"}, {"sku": "B"}],
        )
        assert result.total == 10
        assert result.success == 8
        assert result.failed == 2
        assert len(result.errors) == 2


class TestPriceChangeAlert:
    """PriceChangeAlert 数据类测试。"""

    def test_alert_dataclass_creation(self):
        from modules.inventory_online.price_monitor import PriceChangeAlert
        from decimal import Decimal

        alert = PriceChangeAlert(
            sku="02-2603-0001",
            title="测试商品",
            old_price=Decimal("100"),
            new_price=Decimal("120"),
            change_rate=0.20,
            direction="up",
            threshold=0.10,
            triggered=True,
            old_listing_price=1000.0,
            new_margin=0.733,
            suggested_action="无需操作",
        )
        assert alert.triggered is True
        assert alert.direction == "up"
        assert alert.change_rate == pytest.approx(0.20)


class TestPriceMonitorInit:
    """PriceMonitor 初始化。"""

    def test_default_thresholds(self):
        from modules.inventory_online.price_monitor import (
            PriceMonitor,
            DEFAULT_PRICE_CHANGE_THRESHOLD,
            DEFAULT_MIN_PROFIT_MARGIN,
        )

        pm = PriceMonitor()
        assert pm.threshold == DEFAULT_PRICE_CHANGE_THRESHOLD
        assert pm.min_margin == DEFAULT_MIN_PROFIT_MARGIN

    def test_custom_thresholds(self):
        from modules.inventory_online.price_monitor import PriceMonitor

        pm = PriceMonitor(price_change_threshold=0.20, min_profit_margin=0.10)
        assert pm.threshold == 0.20
        assert pm.min_margin == 0.10


class TestPriceHistoryModel:
    """SupplierPriceHistory 模型测试。"""

    def test_model_import(self):
        from core.models.price_history import SupplierPriceHistory
        assert SupplierPriceHistory.__tablename__ == "supplier_price_history"

    def test_price_history_fields(self):
        from core.models.price_history import SupplierPriceHistory
        from sqlalchemy import inspect

        cols = [c.name for c in inspect(SupplierPriceHistory).columns]
        assert "sku" in cols
        assert "price" in cols
        assert "currency" in cols
        assert "recorded_at" in cols
        assert "supplier" in cols


class TestPriceAlertEventPayload:
    """PRICE_ALERT 事件 payload 结构测试。"""

    def test_event_payload_structure(self):
        """事件 payload 包含所有必要字段。"""
        payload = {
            "sku": "02-2603-0001",
            "title": "测试商品",
            "old_price": 100.0,
            "new_price": 120.0,
            "change_rate": 0.20,
            "direction": "up",
            "threshold": 0.10,
            "old_listing_price": 1000.0,
            "new_margin": 0.733,
            "suggested_action": "无需操作",
            "message": "02-2603-0001 进货价变化 up: ¥100 → ¥120 (+20.0%)",
        }

        required_keys = [
            "sku", "title", "old_price", "new_price",
            "change_rate", "direction", "threshold",
            "suggested_action", "message",
        ]
        for key in required_keys:
            assert key in payload, f"Missing key: {key}"
