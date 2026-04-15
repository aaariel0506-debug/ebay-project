"""
tests/test_stocktake_service.py

Day 21: 库存盘点测试
"""


import pytest


class TestStartStocktake:
    """start_stocktake 逻辑测试。"""

    def test_start_stocktake_creates_record(self, sample_product, db_session):
        """创建盘点单，锁定系统库存快照。"""
        from core.models import Inventory, InventoryType
        from modules.inventory_offline.stocktake_service import StocktakeService

        # 先入库，库存不为零
        inv = Inventory(
            sku=sample_product.sku,
            type=InventoryType.IN,
            quantity=10,
        )
        db_session.add(inv)
        db_session.commit()

        svc = StocktakeService()
        result = svc.start_stocktake(
            skus=[sample_product.sku],
            operator="test",
        )

        assert result["items_count"] == 1
        assert "stocktake_id" in result
        assert "started_at" in result

    def test_start_stocktake_all_skus(self, sample_product, db_session):
        """不指定 skus 时，盘点所有活跃商品。"""
        from modules.inventory_offline.stocktake_service import StocktakeService

        svc = StocktakeService()
        result = svc.start_stocktake()

        assert result["items_count"] >= 1


class TestRecordCount:
    """record_count 逻辑测试。"""

    def test_record_count_updates_items(self, sample_product, db_session):
        """录入实际数量后计算差异。"""
        from core.models import Inventory, InventoryType
        from modules.inventory_offline.stocktake_service import StocktakeService

        # 入库 10 件
        inv = Inventory(
            sku=sample_product.sku,
            type=InventoryType.IN,
            quantity=10,
        )
        db_session.add(inv)
        db_session.commit()

        svc = StocktakeService()
        stocktake = svc.start_stocktake(skus=[sample_product.sku])

        # 清点：实际只有 8 件
        result = svc.record_count(
            stocktake_id=stocktake["stocktake_id"],
            counts={sample_product.sku: 8},
        )

        assert result["items_updated"] == 1
        assert len(result["differences"]) == 1
        assert result["differences"][0]["diff"] == -2  # 少 2 件

    def test_record_count_no_difference(self, sample_product, db_session):
        """实际数量与系统一致，无差异。"""
        from core.models import Inventory, InventoryType
        from modules.inventory_offline.stocktake_service import StocktakeService

        inv = Inventory(
            sku=sample_product.sku,
            type=InventoryType.IN,
            quantity=10,
        )
        db_session.add(inv)
        db_session.commit()

        svc = StocktakeService()
        stocktake = svc.start_stocktake(skus=[sample_product.sku])

        result = svc.record_count(
            stocktake_id=stocktake["stocktake_id"],
            counts={sample_product.sku: 10},
        )

        assert result["items_updated"] == 1
        assert len(result["differences"]) == 0

    def test_record_count_unknown_sku_raises(self, sample_product, db_session):
        """录入不在盘点单中的 SKU 抛出 ValueError。"""
        from modules.inventory_offline.stocktake_service import StocktakeService

        svc = StocktakeService()
        stocktake = svc.start_stocktake(skus=[sample_product.sku])

        with pytest.raises(ValueError, match="不在盘点单中"):
            svc.record_count(
                stocktake_id=stocktake["stocktake_id"],
                counts={"NONEXISTENT-SKU": 5},
            )

    def test_record_count_finished_stocktake_raises(self, sample_product, db_session):
        """已结束的盘点单不能录入。"""
        from core.models import Inventory, InventoryType
        from modules.inventory_offline.stocktake_service import StocktakeService

        inv = Inventory(sku=sample_product.sku, type=InventoryType.IN, quantity=10)
        db_session.add(inv)
        db_session.commit()

        svc = StocktakeService()
        stocktake = svc.start_stocktake(skus=[sample_product.sku])
        svc.finish_stocktake(stocktake["stocktake_id"])

        with pytest.raises(ValueError, match="已结束"):
            svc.record_count(
                stocktake_id=stocktake["stocktake_id"],
                counts={sample_product.sku: 8},
            )


class TestFinishStocktake:
    """finish_stocktake 逻辑测试。"""

    def test_finish_stocktake_creates_adjust_records(self, sample_product, db_session):
        """结束盘点，生成 ADJUST 记录（盘亏 -2）。"""
        from core.models import Inventory, InventoryType
        from modules.inventory_offline.stocktake_service import StocktakeService

        inv = Inventory(sku=sample_product.sku, type=InventoryType.IN, quantity=10)
        db_session.add(inv)
        db_session.commit()

        svc = StocktakeService()
        stocktake = svc.start_stocktake(skus=[sample_product.sku])
        svc.record_count(stocktake_id=stocktake["stocktake_id"], counts={sample_product.sku: 8})
        result = svc.finish_stocktake(stocktake_id=stocktake["stocktake_id"])

        assert result.status == "finished"
        assert result.adjustment_records == 1
        assert result.total_difference == -2  # 盘亏 2 件

    def test_finish_stocktake_no_difference(self, sample_product, db_session):
        """无差异时不生成 ADJUST 记录。"""
        from core.models import Inventory, InventoryType
        from modules.inventory_offline.stocktake_service import StocktakeService

        inv = Inventory(sku=sample_product.sku, type=InventoryType.IN, quantity=10)
        db_session.add(inv)
        db_session.commit()

        svc = StocktakeService()
        stocktake = svc.start_stocktake(skus=[sample_product.sku])
        svc.record_count(stocktake_id=stocktake["stocktake_id"], counts={sample_product.sku: 10})
        result = svc.finish_stocktake(stocktake_id=stocktake["stocktake_id"])

        assert result.adjustment_records == 0
        assert result.total_difference == 0

    def test_finish_stocktake_over_recorded_raises(self, sample_product, db_session):
        """已结束的盘点单不能重复结束。"""
        from core.models import Inventory, InventoryType
        from modules.inventory_offline.stocktake_service import StocktakeService

        inv = Inventory(sku=sample_product.sku, type=InventoryType.IN, quantity=10)
        db_session.add(inv)
        db_session.commit()

        svc = StocktakeService()
        stocktake = svc.start_stocktake(skus=[sample_product.sku])
        svc.record_count(stocktake_id=stocktake["stocktake_id"], counts={sample_product.sku: 8})
        svc.finish_stocktake(stocktake_id=stocktake["stocktake_id"])

        with pytest.raises(ValueError, match="已结束"):
            svc.finish_stocktake(stocktake_id=stocktake["stocktake_id"])


class TestCancelStocktake:
    """cancel_stocktake 逻辑测试。"""

    def test_cancel_in_progress_succeeds(self, sample_product, db_session):
        """IN_PROGRESS 状态可取消。"""
        from modules.inventory_offline.stocktake_service import StocktakeService

        svc = StocktakeService()
        stocktake = svc.start_stocktake(skus=[sample_product.sku])
        result = svc.cancel_stocktake(stocktake_id=stocktake["stocktake_id"])

        assert result["status"] == "cancelled"

    def test_cancel_finished_raises(self, sample_product, db_session):
        """已结束的盘点单不能取消。"""
        from core.models import Inventory, InventoryType
        from modules.inventory_offline.stocktake_service import StocktakeService

        inv = Inventory(sku=sample_product.sku, type=InventoryType.IN, quantity=10)
        db_session.add(inv)
        db_session.commit()

        svc = StocktakeService()
        stocktake = svc.start_stocktake(skus=[sample_product.sku])
        svc.record_count(stocktake_id=stocktake["stocktake_id"], counts={sample_product.sku: 8})
        svc.finish_stocktake(stocktake_id=stocktake["stocktake_id"])

        with pytest.raises(ValueError, match="无法取消"):
            svc.cancel_stocktake(stocktake_id=stocktake["stocktake_id"])
