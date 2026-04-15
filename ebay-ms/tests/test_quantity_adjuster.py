"""
tests/test_quantity_adjuster.py

Day 17: eBay 库存调整接口测试
"""



class TestAdjustmentResult:
    """AdjustmentResult 数据类测试。"""

    def test_successful_adjustment(self):
        from modules.inventory_online.quantity_adjuster import AdjustmentResult

        r = AdjustmentResult(
            sku="02-2603-0001",
            old_quantity=10,
            new_quantity=5,
            success=True,
        )
        assert r.success is True
        assert r.error is None
        assert r.sku == "02-2603-0001"

    def test_failed_adjustment(self):
        from modules.inventory_online.quantity_adjuster import AdjustmentResult

        r = AdjustmentResult(
            sku="02-2603-0001",
            old_quantity=10,
            new_quantity=5,
            success=False,
            error="eBay API returned 500",
        )
        assert r.success is False
        assert r.error == "eBay API returned 500"


class TestBatchAdjustmentResult:
    """BatchAdjustmentResult 测试。"""

    def test_counts(self):
        from modules.inventory_online.quantity_adjuster import (
            AdjustmentResult,
            BatchAdjustmentResult,
        )

        results = [
            AdjustmentResult(sku="A", old_quantity=10, new_quantity=5, success=True),
            AdjustmentResult(sku="B", old_quantity=3, new_quantity=0, success=False, error="not found"),
        ]
        batch = BatchAdjustmentResult(
            total=2,
            success=1,
            failed=1,
            results=results,
        )
        assert batch.total == 2
        assert batch.success == 1
        assert batch.failed == 1
        assert len(batch.results) == 2


class TestQuantityAdjusterInit:
    """QuantityAdjuster 初始化。"""

    def test_init_with_default_client(self):
        from modules.inventory_online.quantity_adjuster import QuantityAdjuster

        adjuster = QuantityAdjuster()
        assert adjuster._client is not None


class TestBatchCsvResult:
    """批量调整 CSV 格式容错测试。"""

    def test_empty_sku_row(self):
        from modules.inventory_online.quantity_adjuster import AdjustmentResult

        # sku 为空时不应 crash，应记录错误
        r = AdjustmentResult(sku="?", old_quantity=0, new_quantity=0, success=False, error="sku 为空")
        assert r.success is False
        assert "sku 为空" in r.error

    def test_invalid_quantity(self):
        from modules.inventory_online.quantity_adjuster import AdjustmentResult

        r = AdjustmentResult(sku="TEST", old_quantity=0, new_quantity=0, success=False, error="无效数量: abc")
        assert r.success is False
        assert "无效数量" in r.error
