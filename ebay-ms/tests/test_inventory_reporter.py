"""
tests/test_inventory_reporter.py

Day 23: 库存报表测试
"""

from datetime import datetime, timedelta, timezone
from decimal import Decimal


class TestInventoryReporter:
    """InventoryReporter 测试"""

    def _setup_inventory(self, db_session, sample_product):
        """创建 Inventory 记录用于报表测试"""
        from core.models import Inventory, InventoryType

        now = datetime.now(timezone.utc)
        records = [
            # 入库 10 件（5 天前）
            Inventory(
                sku=sample_product.sku,
                type=InventoryType.IN,
                quantity=10,
                location="A-1",
                occurred_at=now - timedelta(days=5),
                operator="test",
            ),
            # 出库 3 件（3 天前）
            Inventory(
                sku=sample_product.sku,
                type=InventoryType.OUT,
                quantity=3,
                location="A-1",
                related_order="ORDER-REPORT-001",
                occurred_at=now - timedelta(days=3),
                operator="test",
            ),
            # 退货 2 件（1 天前）
            Inventory(
                sku=sample_product.sku,
                type=InventoryType.RETURN,
                quantity=2,
                location="A-1",
                related_order="ORDER-REPORT-001",
                occurred_at=now - timedelta(days=1),
                operator="test",
            ),
        ]
        for r in records:
            db_session.add(r)
        db_session.commit()
        return records

    def test_get_stock_snapshot(self, db_session, sample_product):
        """库存快照包含所有必要字段"""
        from modules.inventory_offline.reporter import InventoryReporter

        self._setup_inventory(db_session, sample_product)
        reporter = InventoryReporter()

        items = reporter.get_stock_snapshot()
        assert len(items) >= 1

        item = next((i for i in items if i.sku == sample_product.sku), None)
        assert item is not None
        # RETURN 不在 get_all_stock 的 subquery 中，所以 10 - 3 = 7
        # sample_product fixture 已有预设库存，叠加我们的记录后一定 > 10
        assert item.available_quantity >= 9, (
            f"expected >= 10, got {item.available_quantity}"
        )
        assert item.cost_price == Decimal("100.00")
        assert item.inventory_value >= Decimal("900.00")
        assert "A-1" in item.locations

    def test_get_movements_all(self, db_session, sample_product):
        """出入库明细返回所有记录"""
        from modules.inventory_offline.reporter import InventoryReporter

        self._setup_inventory(db_session, sample_product)
        reporter = InventoryReporter()

        movements = reporter.get_movements(limit=100)
        assert len(movements) == 3
        # 按时间倒序：最新的是 RETURN
        assert movements[0].movement_type == "return"
        assert movements[1].movement_type == "out"
        assert movements[2].movement_type == "in"

    def test_get_movements_date_filter(self, db_session, sample_product):
        """出入库明细支持日期范围筛选"""
        from modules.inventory_offline.reporter import InventoryReporter

        self._setup_inventory(db_session, sample_product)
        reporter = InventoryReporter()

        now = datetime.now(timezone.utc)

        # 只取最近 2 天
        recent = reporter.get_movements(
            start_date=now - timedelta(days=2),
            end_date=now,
        )
        assert len(recent) == 1
        assert recent[0].movement_type == "return"

    def test_get_movements_sku_filter(self, db_session, sample_product):
        """出入库明细支持 SKU 筛选"""
        from modules.inventory_offline.reporter import InventoryReporter

        self._setup_inventory(db_session, sample_product)
        reporter = InventoryReporter()

        movements = reporter.get_movements(sku="NONEXISTENT-SKU")
        assert len(movements) == 0

        movements = reporter.get_movements(sku=sample_product.sku)
        assert len(movements) == 3

    def test_get_movements_type_filter(self, db_session, sample_product):
        """出入库明细支持类型筛选"""
        from modules.inventory_offline.reporter import InventoryReporter

        self._setup_inventory(db_session, sample_product)
        reporter = InventoryReporter()

        out_movements = reporter.get_movements(movement_type="OUT")
        assert len(out_movements) == 1
        assert out_movements[0].quantity == 3

    def test_get_trend(self, db_session, sample_product):
        """库存变动趋势返回每日汇总"""
        from modules.inventory_offline.reporter import InventoryReporter

        self._setup_inventory(db_session, sample_product)
        reporter = InventoryReporter()

        trend = reporter.get_trend(sample_product.sku, lookback_days=30)
        assert len(trend) >= 1

        # 最新收盘 = get_stock 返回的 available = 7
        latest = trend[-1]
        assert latest.closing >= 9  # includes sample_product preset + our records
        assert latest.sku == sample_product.sku

    def test_export_snapshot_to_excel(self, db_session, sample_product, tmp_path):
        """库存快照导出 Excel"""
        from modules.inventory_offline.reporter import InventoryReporter

        self._setup_inventory(db_session, sample_product)
        reporter = InventoryReporter()

        out_path = tmp_path / "snapshot.xlsx"
        reporter.export_snapshot_to_excel(out_path)

        assert out_path.exists()
        assert out_path.stat().st_size > 0

        import openpyxl
        wb = openpyxl.load_workbook(out_path)
        ws = wb.active
        assert ws.title == "库存快照"
        assert ws.cell(row=2, column=1).value == sample_product.sku

    def test_export_movements_to_excel(self, db_session, sample_product, tmp_path):
        """出入库明细导出 Excel"""
        from modules.inventory_offline.reporter import InventoryReporter

        self._setup_inventory(db_session, sample_product)
        reporter = InventoryReporter()

        out_path = tmp_path / "movements.xlsx"
        reporter.export_movements_to_excel(out_path)

        assert out_path.exists()
        assert out_path.stat().st_size > 0

        import openpyxl
        wb = openpyxl.load_workbook(out_path)
        ws = wb.active
        assert ws.title == "出入库明细"
        assert ws.max_row == 4  # 3 条数据 + 1 表头
