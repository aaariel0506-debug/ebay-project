"""
tests/test_inbound_service.py

Day 19: 入库功能测试
"""

from decimal import Decimal

import pytest
from modules.inventory_offline.inbound_service import (
    InboundItemInput,
    InboundService,
    ReceivedItemInput,
)


class TestCreateReceipt:
    """create_receipt 逻辑测试。"""

    def test_create_receipt_generates_receipt_no(self, sample_product):
        """不传 receipt_no 时自动生成 IN-YYYY-MM-DD-NNN 格式。"""
        svc = InboundService()
        result = svc.create_receipt(
            supplier="Test Supplier",
            items=[InboundItemInput(sku="TEST-SKU-001", expected_quantity=10, cost_price=Decimal("100"))],
        )
        assert result.receipt_no.startswith("IN-")
        assert result.status == "pending"
        assert result.item_count == 1

    def test_create_receipt_with_custom_receipt_no(self, sample_product):
        """传入 receipt_no 时使用指定值。"""
        svc = InboundService()
        result = svc.create_receipt(
            receipt_no="IN-2026-04-16-TEST",
            supplier="Test Supplier",
            items=[InboundItemInput(sku="TEST-SKU-001", expected_quantity=5, cost_price=Decimal("200"))],
        )
        assert result.receipt_no == "IN-2026-04-16-TEST"

    def test_create_receipt_empty_items_raises(self):
        """物品列表为空时抛出 ValueError。"""
        svc = InboundService()
        with pytest.raises(ValueError, match="物品列表不能为空"):
            svc.create_receipt(supplier="Test", items=[])

    def test_create_receipt_nonexistent_sku_raises(self):
        """SKU 不存在时抛出 ValueError。"""
        svc = InboundService()
        with pytest.raises(ValueError, match="SKU 不存在"):
            svc.create_receipt(
                supplier="Test",
                items=[InboundItemInput(sku="NONEXISTENT-SKU", expected_quantity=1, cost_price=Decimal("100"))],
            )


class TestConfirmInbound:
    """confirm_inbound 逻辑测试。"""

    def test_confirm_inbound_partial(self, sample_product, db_session):
        """部分收货：received_quantity < expected_quantity，状态变为 PARTIAL。"""
        from core.models import InboundReceipt, InboundReceiptItem, InboundStatus

        # 创建入库单
        receipt = InboundReceipt(
            receipt_no="IN-TEST-PARTIAL",
            supplier="Test Supplier",
            status=InboundStatus.PENDING,
        )
        db_session.add(receipt)
        db_session.flush()

        item = InboundReceiptItem(
            receipt_id=receipt.id,
            sku=sample_product.sku,
            expected_quantity=10,
            received_quantity=0,
            cost_price=Decimal("100"),
        )
        db_session.add(item)
        db_session.commit()

        svc = InboundService()
        result = svc.confirm_inbound(
            receipt_id=receipt.id,
            received_items=[ReceivedItemInput(sku=sample_product.sku, received_quantity=6)],
            operator="test",
        )

        assert result.status == "partial"
        assert result.items_confirmed == 1
        assert result.total_received == 6
        assert result.inventory_records == 1

    def test_confirm_inbound_full(self, sample_product, db_session):
        """全部收货：received_quantity >= expected_quantity，状态变为 RECEIVED。"""
        from core.models import InboundReceipt, InboundReceiptItem, InboundStatus

        receipt = InboundReceipt(
            receipt_no="IN-TEST-FULL",
            supplier="Test Supplier",
            status=InboundStatus.PENDING,
        )
        db_session.add(receipt)
        db_session.flush()

        item = InboundReceiptItem(
            receipt_id=receipt.id,
            sku=sample_product.sku,
            expected_quantity=10,
            received_quantity=0,
            cost_price=Decimal("150"),
        )
        db_session.add(item)
        db_session.commit()

        svc = InboundService()
        result = svc.confirm_inbound(
            receipt_id=receipt.id,
            received_items=[ReceivedItemInput(sku=sample_product.sku, received_quantity=10)],
            operator="test",
        )

        assert result.status == "received"
        assert result.inventory_records == 1

    def test_confirm_inbound_over_received(self, sample_product, db_session):
        """超量收货：received > expected，仍计入库存，状态 RECEIVED。"""
        from core.models import InboundReceipt, InboundReceiptItem, InboundStatus

        receipt = InboundReceipt(
            receipt_no="IN-TEST-OVER",
            supplier="Test Supplier",
            status=InboundStatus.PENDING,
        )
        db_session.add(receipt)
        db_session.flush()

        item = InboundReceiptItem(
            receipt_id=receipt.id,
            sku=sample_product.sku,
            expected_quantity=5,
            received_quantity=0,
            cost_price=Decimal("80"),
        )
        db_session.add(item)
        db_session.commit()

        svc = InboundService()
        result = svc.confirm_inbound(
            receipt_id=receipt.id,
            received_items=[ReceivedItemInput(sku=sample_product.sku, received_quantity=8)],
        )

        assert result.status == "received"
        assert result.total_received == 8
        assert result.inventory_records == 1

    def test_confirm_inbound_nonexistent_receipt_raises(self):
        """入库单不存在时抛出 ValueError。"""
        svc = InboundService()
        with pytest.raises(ValueError, match="入库单不存在"):
            svc.confirm_inbound(
                receipt_id=99999,
                received_items=[ReceivedItemInput(sku="TEST-SKU", received_quantity=1)],
            )

    def test_confirm_inbound_already_received_raises(self, sample_product, db_session):
        """状态为 RECEIVED 的入库单不能重复确认。"""
        from core.models import InboundReceipt, InboundReceiptItem, InboundStatus

        receipt = InboundReceipt(
            receipt_no="IN-TEST-DONE",
            supplier="Test",
            status=InboundStatus.RECEIVED,
        )
        db_session.add(receipt)
        db_session.flush()

        item = InboundReceiptItem(
            receipt_id=receipt.id,
            sku=sample_product.sku,
            expected_quantity=10,
            received_quantity=10,
            cost_price=Decimal("100"),
        )
        db_session.add(item)
        db_session.commit()

        svc = InboundService()
        with pytest.raises(ValueError, match="已全部收货"):
            svc.confirm_inbound(
                receipt_id=receipt.id,
                received_items=[ReceivedItemInput(sku=sample_product.sku, received_quantity=5)],
            )


class TestGetReceipt:
    """get_receipt 逻辑测试。"""

    def test_get_receipt_returns_items(self, sample_product, db_session):
        """返回入库单含完整物品明细。"""
        from core.models import InboundReceipt, InboundReceiptItem, InboundStatus

        receipt = InboundReceipt(
            receipt_no="IN-TEST-GET",
            supplier="Test Supplier",
            status=InboundStatus.PENDING,
        )
        db_session.add(receipt)
        db_session.flush()

        item = InboundReceiptItem(
            receipt_id=receipt.id,
            sku=sample_product.sku,
            expected_quantity=20,
            received_quantity=5,
            cost_price=Decimal("250"),
        )
        db_session.add(item)
        db_session.commit()

        svc = InboundService()
        result = svc.get_receipt(receipt.id)

        assert result["receipt_no"] == "IN-TEST-GET"
        assert result["status"] == "pending"
        assert len(result["items"]) == 1
        assert result["items"][0]["sku"] == sample_product.sku
        assert result["items"][0]["expected_quantity"] == 20
        assert result["items"][0]["received_quantity"] == 5


class TestListReceipts:
    """list_receipts 逻辑测试。"""

    def test_list_receipts_by_status(self, sample_product, db_session):
        """按状态筛选返回正确结果。"""
        from core.models import InboundReceipt, InboundStatus

        for i, status in enumerate([InboundStatus.PENDING, InboundStatus.RECEIVED, InboundStatus.PENDING]):
            r = InboundReceipt(receipt_no=f"IN-TEST-LIST-{i}", supplier="Test", status=status)
            db_session.add(r)
        db_session.commit()

        svc = InboundService()
        pending = svc.list_receipts(status="pending")
        received = svc.list_receipts(status="received")

        assert all(item["status"] == "pending" for item in pending)
        assert all(item["status"] == "received" for item in received)


class TestCancelReceipt:
    """cancel_receipt 逻辑测试。"""

    def test_cancel_pending_receipt(self, sample_product, db_session):
        """PENDING 状态可正常取消。"""
        from core.models import InboundReceipt, InboundStatus

        receipt = InboundReceipt(
            receipt_no="IN-TEST-CANCEL",
            supplier="Test",
            status=InboundStatus.PENDING,
        )
        db_session.add(receipt)
        db_session.commit()

        svc = InboundService()
        result = svc.cancel_receipt(receipt.id)

        assert result["status"] == "cancelled"

    def test_cancel_received_receipt_raises(self, sample_product, db_session):
        """RECEIVED 状态无法取消。"""
        from core.models import InboundReceipt, InboundStatus

        receipt = InboundReceipt(
            receipt_no="IN-TEST-CANCEL-DONE",
            supplier="Test",
            status=InboundStatus.RECEIVED,
        )
        db_session.add(receipt)
        db_session.commit()

        svc = InboundService()
        with pytest.raises(ValueError, match="无法取消"):
            svc.cancel_receipt(receipt.id)


class TestOutbound:
    """outbound / return_inventory 逻辑测试。"""

    def test_outbound_success(self, sample_product, db_session):
        """正常出库：库存充足，创建 OUT 记录，发布 STOCK_OUT 事件。"""
        from core.models import Inventory, InventoryType

        # 先入库 10 件
        inv_in = Inventory(
            sku=sample_product.sku,
            type=InventoryType.IN,
            quantity=10,
            operator="setup",
        )
        db_session.add(inv_in)
        db_session.commit()

        svc = InboundService()
        result = svc.outbound(
            sku=sample_product.sku,
            quantity=3,
            related_order="ORDER-001",
            operator="test",
        )

        assert result["quantity"] == 3
        assert result["remaining_stock"] == 7

    def test_outbound_insufficient_raises(self, sample_product, db_session):
        """库存不足时抛出 ValueError。"""
        from core.models import Inventory, InventoryType

        # 只入库 5 件
        inv_in = Inventory(
            sku=sample_product.sku,
            type=InventoryType.IN,
            quantity=5,
        )
        db_session.add(inv_in)
        db_session.commit()

        svc = InboundService()
        with pytest.raises(ValueError, match="库存不足"):
            svc.outbound(sku=sample_product.sku, quantity=10)

    def test_outbound_zero_quantity_raises(self, sample_product):
        """出库数量 <= 0 时抛出 ValueError。"""
        svc = InboundService()
        with pytest.raises(ValueError, match="出库数量必须"):
            svc.outbound(sku=sample_product.sku, quantity=0)

    def test_return_inventory_success(self, sample_product, db_session):
        """退货入库：创建 RETURN 记录，发布 STOCK_RETURN 事件。"""
        svc = InboundService()
        result = svc.return_inventory(
            sku=sample_product.sku,
            quantity=2,
            related_order="ORDER-002",
            operator="test",
        )
        assert result["quantity"] == 2
        assert result["sku"] == sample_product.sku

    def test_list_outbound_filters(self, sample_product, db_session):
        """按 SKU / 订单号筛选出库记录。"""
        from core.models import Inventory, InventoryType

        for qty, order in [(5, "A"), (3, "B"), (2, "A")]:
            inv = Inventory(
                sku=sample_product.sku,
                type=InventoryType.OUT,
                quantity=qty,
                related_order=order,
            )
            db_session.add(inv)
        db_session.commit()

        svc = InboundService()
        all_rows = svc.list_outbound(sku=sample_product.sku)
        order_a = svc.list_outbound(related_order="A")

        assert len(all_rows) == 3
        assert len(order_a) == 2
        assert all(r["related_order"] == "A" for r in order_a)
