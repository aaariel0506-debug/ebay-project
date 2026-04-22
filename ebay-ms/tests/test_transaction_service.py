"""tests/test_transaction_service.py

Day 27 — TransactionService 测试套件（15 tests）

测试场景：
  1.  2-SKU 订单 rebuild 后：2 SALE + 1 FEE + 1 SHIPPING = 4 条
  2.  守恒 1/2/3/4/5 全验证
  3.  Product.cost_price 存在时：unit_cost/total_cost/profit/margin 全填
  4.  Product 不存在时：unit_cost=None，不抛错
  5.  overwrite=True 替换旧记录（deleted_count > 0）
  6.  overwrite=False 已有 Transaction 时跳过
  7.  ebay_fee=0 → fee_count=0，表中无 FEE 记录
  8.  shipping_cost=0 → shipping_count=0，表中无 SHIPPING 记录
  9.  REFUND 不受 rebuild 影响（只清 SALE/FEE/SHIPPING）
  10. order_id 不存在 → ValueError
  11. 只有 Order 无 OrderItem → skipped_reason="no_order_items"
  12. rebuild_all：3 订单 1 失败 2 成功，返回 3 条 RebuildResult
  13. list_by_order 返回所有类型（按 id 升序）
  14. list_by_type + date_range 过滤
  15. list_by_date_range
"""

from datetime import datetime
from decimal import Decimal

import pytest
from core.models import Base, Order, OrderItem, OrderStatus, Product, ProductStatus, Transaction, TransactionType
from modules.finance.transaction_service import TransactionService
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker


class TestTransactionService:
    """TransactionService 重建逻辑测试。"""

    @pytest.fixture
    def sess(self) -> Session:
        """独立 in-memory DB，每个测试 fresh。"""
        engine = create_engine("sqlite:///:memory:", echo=False)
        Base.metadata.create_all(engine)
        Session = sessionmaker(bind=engine)
        s = Session()
        yield s
        s.close()

    # ── Fixtures ─────────────────────────────────────────────────────────

    def _make_product(
        self, sess: Session, sku: str, cost_price: float | Decimal = "10.00"
    ) -> Product:
        p = Product(
            sku=sku,
            title=f"Test Product {sku}",
            status=ProductStatus.ACTIVE,
            cost_price=Decimal(str(cost_price)),
        )
        sess.add(p)
        sess.commit()
        return p

    def _make_order(
        self,
        sess: Session,
        order_id: str,
        sale_price: float = "100.00",
        ebay_fee: float = "8.00",
        shipping_cost: float = "5.00",
        order_date: datetime | None = None,
    ) -> Order:
        if order_date is None:
            order_date = datetime(2026, 4, 15, 10, 0, 0)
        o = Order(
            ebay_order_id=order_id,
            sale_price=Decimal(str(sale_price)),
            ebay_fee=Decimal(str(ebay_fee)),
            shipping_cost=Decimal(str(shipping_cost)),
            status=OrderStatus.SHIPPED,
            order_date=order_date,
        )
        sess.add(o)
        sess.commit()
        return o

    def _make_order_item(
        self,
        sess: Session,
        order_id: str,
        sku: str,
        sale_amount: float = "50.00",
        quantity: int = 1,
    ) -> OrderItem:
        item = OrderItem(
            order_id=order_id,
            sku=sku,
            quantity=quantity,
            unit_price=Decimal(str(sale_amount)),
            sale_amount=Decimal(str(sale_amount)),
        )
        sess.add(item)
        sess.commit()
        return item

    def _tx_count(self, sess: Session, order_id: str, tx_type: TransactionType | None = None) -> int:
        q = sess.query(Transaction).filter(Transaction.order_id == order_id)
        if tx_type:
            q = q.filter(Transaction.type == tx_type)
        return q.count()

    # ── 测试 1：基本写入 ─────────────────────────────────────────────────

    def test_rebuild_single_order_writes_sale_fee_shipping(self, sess: Session):
        """
        2-SKU 订单，rebuild 后 Transaction 表有：
          2 SALE（每 SKU 一条）+ 1 FEE（order-level）+ 1 SHIPPING（order-level）= 4 条
        """
        self._make_product(sess, "SKU-A", "10.00")
        self._make_product(sess, "SKU-B", "20.00")
        self._make_order(sess, "ORD-2SKU", sale_price="100.00", ebay_fee="8.00", shipping_cost="5.00")
        self._make_order_item(sess, "ORD-2SKU", "SKU-A", sale_amount="50.00", quantity=1)
        self._make_order_item(sess, "ORD-2SKU", "SKU-B", sale_amount="50.00", quantity=1)

        svc = TransactionService(session=sess)
        result = svc.rebuild_for_order("ORD-2SKU")

        assert result.sale_count == 2
        assert result.fee_count == 1
        assert result.shipping_count == 1
        assert self._tx_count(sess, "ORD-2SKU") == 4

        # FEE 和 SHIPPING 的 sku 为 NULL
        fee = sess.query(Transaction).filter(
            Transaction.order_id == "ORD-2SKU", Transaction.type == TransactionType.FEE
        ).first()
        assert fee is not None
        assert fee.sku is None
        assert fee.amount == -8.00

        shipping = sess.query(Transaction).filter(
            Transaction.order_id == "ORD-2SKU", Transaction.type == TransactionType.SHIPPING
        ).first()
        assert shipping is not None
        assert shipping.sku is None
        assert shipping.amount == 5.00

    # ── 测试 2：守恒不变量 ───────────────────────────────────────────────

    def test_rebuild_preserves_conservation_invariants(self, sess: Session):
        """
        验证 5 条守恒不变量（对一个 1-SKU 订单）：
          1. sum(SALE.amount) == Order.sale_price
          2. sum(FEE.amount) == -Order.ebay_fee
          3. sum(SHIPPING.amount) == Order.shipping_cost
          4. count(SALE) == count(OrderItem)
          5. count(FEE) <= 1 and count(SHIPPING) <= 1
        """
        self._make_product(sess, "SKU-X", "30.00")
        self._make_order(
            sess, "ORD-INV", sale_price="100.00", ebay_fee="8.00", shipping_cost="5.00"
        )
        self._make_order_item(sess, "ORD-INV", "SKU-X", sale_amount="100.00", quantity=1)

        order = sess.query(Order).filter(Order.ebay_order_id == "ORD-INV").first()
        items_count = sess.query(OrderItem).filter(OrderItem.order_id == "ORD-INV").count()

        svc = TransactionService(session=sess)
        svc.rebuild_for_order("ORD-INV")

        # 汇总
        sales = sess.query(Transaction).filter(
            Transaction.order_id == "ORD-INV", Transaction.type == TransactionType.SALE
        ).all()
        fee_row = sess.query(Transaction).filter(
            Transaction.order_id == "ORD-INV", Transaction.type == TransactionType.FEE
        ).first()
        shipping_row = sess.query(Transaction).filter(
            Transaction.order_id == "ORD-INV", Transaction.type == TransactionType.SHIPPING
        ).first()

        assert sum(t.amount for t in sales) == pytest.approx(float(order.sale_price))
        assert (fee_row.amount if fee_row else 0) == pytest.approx(-float(order.ebay_fee))
        assert (shipping_row.amount if shipping_row else 0) == pytest.approx(
            float(order.shipping_cost)
        )
        assert len(sales) == items_count
        assert len(sales) <= items_count  # count(SALE) == count(OrderItem)
        assert len([t for t in sales if t.type == TransactionType.FEE]) <= 1
        assert len([t for t in sales if t.type == TransactionType.SHIPPING]) <= 1

    # ── 测试 3：cost / profit / margin 填充 ─────────────────────────────

    def test_rebuild_sale_populates_cost_profit_margin(self, sess: Session):
        """
        Product.cost_price 存在时：unit_cost / total_cost / profit / margin 全填。
        验证：unit_cost = cost_price, total_cost = cost_price × qty,
              profit = amount - total_cost, margin = profit / amount
        """
        self._make_product(sess, "SKU-COST", "30.00")
        self._make_order(sess, "ORD-COST", sale_price="100.00", ebay_fee="5.00", shipping_cost="0")
        self._make_order_item(sess, "ORD-COST", "SKU-COST", sale_amount="100.00", quantity=1)

        svc = TransactionService(session=sess)
        svc.rebuild_for_order("ORD-COST")

        sale = sess.query(Transaction).filter(
            Transaction.order_id == "ORD-COST",
            Transaction.type == TransactionType.SALE,
            Transaction.sku == "SKU-COST",
        ).first()

        assert sale is not None
        assert sale.unit_cost == Decimal("30.00")
        assert sale.total_cost == Decimal("30.00")
        assert sale.profit == Decimal("70.00")
        assert sale.margin == pytest.approx(Decimal("0.70"))

    # ── 测试 4：Product 不存在 ──────────────────────────────────────────

    def test_rebuild_sale_handles_missing_product(self, sess: Session):
        """
        Product 不存在时：unit_cost=None, total_cost=None, profit=None, margin=None。
        不抛错，rebuild 正常完成。
        """
        self._make_order(sess, "ORD-NO-PROD", sale_price="50.00", ebay_fee="0", shipping_cost="0")
        self._make_order_item(sess, "ORD-NO-PROD", "UNKNOWN-SKU", sale_amount="50.00", quantity=1)

        svc = TransactionService(session=sess)
        result = svc.rebuild_for_order("ORD-NO-PROD")

        assert result.sale_count == 1
        sale = sess.query(Transaction).filter(
            Transaction.order_id == "ORD-NO-PROD", Transaction.type == TransactionType.SALE
        ).first()
        assert sale.unit_cost is None
        assert sale.total_cost is None
        assert sale.profit is None
        assert sale.margin is None

    # ── 测试 5：overwrite=True 替换旧记录 ──────────────────────────────

    def test_rebuild_overwrite_true_replaces_old_transactions(self, sess: Session):
        """
        第一次 rebuild，再手动改一条 SALE.amount，再 rebuild(overwrite=True)：
          - deleted_count > 0（旧记录被清）
          - 改动的值被覆盖回正确值
        """
        self._make_product(sess, "SKU-OW", "10.00")
        self._make_order(sess, "ORD-OW", sale_price="50.00", ebay_fee="3.00", shipping_cost="2.00")
        self._make_order_item(sess, "ORD-OW", "SKU-OW", sale_amount="50.00", quantity=1)

        svc = TransactionService(session=sess)
        r1 = svc.rebuild_for_order("ORD-OW")
        assert r1.deleted_count == 0  # 第一次无旧记录

        # 手动改 SALE amount
        sale = sess.query(Transaction).filter(
            Transaction.order_id == "ORD-OW", Transaction.type == TransactionType.SALE
        ).first()
        sale.amount = 999.99
        sess.commit()

        # overwrite=True 再次 rebuild
        r2 = svc.rebuild_for_order("ORD-OW", overwrite=True)
        assert r2.deleted_count > 0
        sale_updated = sess.query(Transaction).filter(
            Transaction.order_id == "ORD-OW", Transaction.type == TransactionType.SALE
        ).first()
        assert sale_updated.amount == 50.00  # 被覆盖回正确值

    # ── 测试 6：overwrite=False 跳过 ──────────────────────────────────

    def test_rebuild_overwrite_false_skips_when_exists(self, sess: Session):
        """已有 SALE/FEE/SHIPPING 时 overwrite=False → skipped_reason="already_has_transactions"。"""
        self._make_product(sess, "SKU-SKIP", "5.00")
        self._make_order(sess, "ORD-SKIP", sale_price="20.00", ebay_fee="1.00", shipping_cost="0")
        self._make_order_item(sess, "ORD-SKIP", "SKU-SKIP", sale_amount="20.00", quantity=1)

        svc = TransactionService(session=sess)
        r1 = svc.rebuild_for_order("ORD-SKIP", overwrite=False)
        assert r1.sale_count == 1

        # 再次 rebuild（已有记录）
        r2 = svc.rebuild_for_order("ORD-SKIP", overwrite=False)
        assert r2.skipped_reason == "already_has_transactions"
        assert r2.sale_count == 0

    # ── 测试 7：ebay_fee=0 无 FEE ─────────────────────────────────────

    def test_rebuild_zero_fee_no_fee_transaction(self, sess: Session):
        """Order.ebay_fee=0 → fee_count=0，表中无 FEE 记录。"""
        self._make_product(sess, "SKU-NOFEE", "5.00")
        self._make_order(sess, "ORD-NOFEE", sale_price="20.00", ebay_fee="0", shipping_cost="2.00")
        self._make_order_item(sess, "ORD-NOFEE", "SKU-NOFEE", sale_amount="20.00", quantity=1)

        svc = TransactionService(session=sess)
        result = svc.rebuild_for_order("ORD-NOFEE")

        assert result.fee_count == 0
        assert self._tx_count(sess, "ORD-NOFEE", TransactionType.FEE) == 0

    # ── 测试 8：shipping_cost=0 无 SHIPPING ─────────────────────────

    def test_rebuild_zero_shipping_no_shipping_transaction(self, sess: Session):
        """Order.shipping_cost=0 → shipping_count=0，表中无 SHIPPING 记录。"""
        self._make_product(sess, "SKU-NOSHIP", "5.00")
        self._make_order(sess, "ORD-NOSHIP", sale_price="20.00", ebay_fee="1.00", shipping_cost="0")
        self._make_order_item(sess, "ORD-NOSHIP", "SKU-NOSHIP", sale_amount="20.00", quantity=1)

        svc = TransactionService(session=sess)
        result = svc.rebuild_for_order("ORD-NOSHIP")

        assert result.shipping_count == 0
        assert self._tx_count(sess, "ORD-NOSHIP", TransactionType.SHIPPING) == 0

    # ── 测试 9：REFUND 不受影响 ───────────────────────────────────────

    def test_rebuild_preserves_refund_transactions(self, sess: Session):
        """
        预先插入一条 REFUND Transaction，
        rebuild（overwrite=True）后 REFUND 还在（只清 SALE/FEE/SHIPPING）。
        """
        self._make_product(sess, "SKU-REF", "5.00")
        self._make_order(sess, "ORD-REF", sale_price="20.00", ebay_fee="1.00", shipping_cost="2.00")
        self._make_order_item(sess, "ORD-REF", "SKU-REF", sale_amount="20.00", quantity=1)

        # 预先插入 REFUND（模拟之前已有的记录）
        refund_tx = Transaction(
            order_id="ORD-REF",
            type=TransactionType.REFUND,
            amount=-10.00,
            currency="USD",
            date=datetime(2026, 4, 15),
            sku=None,
        )
        sess.add(refund_tx)
        sess.commit()

        svc = TransactionService(session=sess)
        svc.rebuild_for_order("ORD-REF", overwrite=True)

        # REFUND 仍存在
        refund_count = self._tx_count(sess, "ORD-REF", TransactionType.REFUND)
        assert refund_count == 1
        refund_row = sess.query(Transaction).filter(
            Transaction.order_id == "ORD-REF", Transaction.type == TransactionType.REFUND
        ).first()
        assert refund_row.amount == -10.00

        # SALE/FEE/SHIPPING 正常写入
        assert self._tx_count(sess, "ORD-REF", TransactionType.SALE) == 1
        assert self._tx_count(sess, "ORD-REF", TransactionType.FEE) == 1
        assert self._tx_count(sess, "ORD-REF", TransactionType.SHIPPING) == 1

    # ── 测试 10：order_id 不存在 ──────────────────────────────────────

    def test_rebuild_order_not_found_raises(self, sess: Session):
        """order_id 不存在 → ValueError。"""
        svc = TransactionService(session=sess)
        with pytest.raises(ValueError, match="order_not_found"):
            svc.rebuild_for_order("NON-EXISTENT")

    # ── 测试 11：无 OrderItem ─────────────────────────────────────────

    def test_rebuild_order_without_line_items_returns_skipped(self, sess: Session):
        """
        只有 Order 无 OrderItem → skipped_reason="no_order_items"，表中无 Transaction。
        （没有可核算的 SKU，连 FEE/SHIPPING 也不写）
        """
        self._make_order(sess, "ORD-EMPTY", sale_price="0", ebay_fee="5.00", shipping_cost="2.00")

        svc = TransactionService(session=sess)
        result = svc.rebuild_for_order("ORD-EMPTY")

        assert result.skipped_reason == "no_order_items"
        assert result.sale_count == 0
        assert self._tx_count(sess, "ORD-EMPTY") == 0

    # ── 测试 12：rebuild_all 部分成功 ────────────────────────────────

    def test_rebuild_all_one_order_fails_others_succeed(self, sess: Session):
        """
        3 个订单，1 个不存在，2 个正常。
        rebuild_all 返回 3 条 RebuildResult。
        """
        # 订单1：正常
        self._make_product(sess, "SKU-G1", "5.00")
        self._make_order(sess, "ORD-G1", sale_price="20.00", ebay_fee="0", shipping_cost="0")
        self._make_order_item(sess, "ORD-G1", "SKU-G1", sale_amount="20.00", quantity=1)
        # 订单2：Order 无 OrderItem（跳过）
        self._make_order(sess, "ORD-G2", sale_price="30.00", ebay_fee="0", shipping_cost="0")
        # 订单3：Product 不存在但 OrderItem 在（可写 SALE，cost=None）
        self._make_order(sess, "ORD-G3", sale_price="40.00", ebay_fee="0", shipping_cost="0")
        self._make_order_item(sess, "ORD-G3", "SKU-NO-PROD-G3", sale_amount="40.00", quantity=1)

        svc = TransactionService(session=sess)
        results = svc.rebuild_all(date_from=datetime(2026, 1, 1), date_to=datetime(2026, 12, 31))

        assert len(results) == 3
        by_id = {r.order_id: r for r in results}

        assert by_id["ORD-G1"].sale_count == 1
        assert by_id["ORD-G2"].skipped_reason == "no_order_items"
        assert by_id["ORD-G3"].sale_count == 1

    # ── 测试 13：list_by_order ────────────────────────────────────────

    def test_list_by_order_returns_all_types_ordered_by_id(self, sess: Session):
        """list_by_order 返回该订单所有类型，按 id 升序。"""
        self._make_product(sess, "SKU-LBO", "5.00")
        self._make_order(sess, "ORD-LBO", sale_price="50.00", ebay_fee="3.00", shipping_cost="2.00")
        self._make_order_item(sess, "ORD-LBO", "SKU-LBO", sale_amount="50.00", quantity=1)

        svc = TransactionService(session=sess)
        svc.rebuild_for_order("ORD-LBO")

        # 手加一条 REFUND
        sess.add(Transaction(
            order_id="ORD-LBO", type=TransactionType.REFUND,
            amount=-10.00, currency="USD", date=datetime(2026, 4, 15), sku=None,
        ))
        sess.commit()

        txs = svc.list_by_order("ORD-LBO")
        ids = [t.id for t in txs]
        assert ids == sorted(ids)  # 升序
        types = [t.type for t in txs]
        assert TransactionType.SALE in types
        assert TransactionType.FEE in types
        assert TransactionType.SHIPPING in types
        assert TransactionType.REFUND in types

    # ── 测试 14：list_by_type + date_range ───────────────────────────

    def test_list_by_type_with_date_range(self, sess: Session):
        """list_by_type + date_from / date_to 正确过滤。"""
        self._make_product(sess, "SKU-LBT", "5.00")
        # 订单在 2026-04-15
        self._make_order(sess, "ORD-LBT", sale_price="20.00", ebay_fee="0", shipping_cost="0",
                         order_date=datetime(2026, 4, 15))
        self._make_order_item(sess, "ORD-LBT", "SKU-LBT", sale_amount="20.00", quantity=1)

        svc = TransactionService(session=sess)
        svc.rebuild_for_order("ORD-LBT")

        # 在范围内
        in_range = svc.list_by_type(
            TransactionType.SALE,
            date_from=datetime(2026, 4, 1),
            date_to=datetime(2026, 4, 30),
        )
        assert len(in_range) >= 1

        # 在范围外
        out_range = svc.list_by_type(
            TransactionType.SALE,
            date_from=datetime(2026, 5, 1),
            date_to=datetime(2026, 5, 31),
        )
        assert all(t.date.month != 4 for t in out_range)

    # ── 测试 15：list_by_date_range ──────────────────────────────────

    def test_list_by_date_range(self, sess: Session):
        """list_by_date_range 返回指定范围内所有 Transaction。"""
        self._make_product(sess, "SKU-LBR", "5.00")
        self._make_order(sess, "ORD-LBR", sale_price="20.00", ebay_fee="1.00", shipping_cost="0",
                         order_date=datetime(2026, 4, 10))
        self._make_order_item(sess, "ORD-LBR", "SKU-LBR", sale_amount="20.00", quantity=1)

        svc = TransactionService(session=sess)
        svc.rebuild_for_order("ORD-LBR")

        txs = svc.list_by_date_range(
            datetime(2026, 4, 1), datetime(2026, 4, 30)
        )
        assert len(txs) >= 2  # SALE + FEE
        assert all(datetime(2026, 4, 1) <= t.date <= datetime(2026, 4, 30) for t in txs)

    # ── 额外：sku 维度验证（2-SKU 各 quantity>1）────────────────────

    def test_sale_amount_uses_quantity_multiplier(self, sess: Session):
        """
        quantity=3，sale_amount=10（per unit）→ amount 应为 30。
        验证：amount = sale_amount × quantity。

        注意：amount = sale_amount × qty，total_cost = cost_price × qty。
        """
        self._make_product(sess, "SKU-QTY", "10.00")
        self._make_order(sess, "ORD-QTY", sale_price="30.00", ebay_fee="0", shipping_cost="0")
        # sale_amount = 10.00 (per unit)，qty = 3 → amount = 30
        self._make_order_item(sess, "ORD-QTY", "SKU-QTY", sale_amount="10.00", quantity=3)

        svc = TransactionService(session=sess)
        svc.rebuild_for_order("ORD-QTY")

        sale = sess.query(Transaction).filter(
            Transaction.order_id == "ORD-QTY",
            Transaction.type == TransactionType.SALE,
        ).first()
        assert sale is not None
        # amount = 10 × 3 = 30，total_cost = 10 × 3 = 30，profit = 30 - 30 = 0
        assert float(sale.amount) == pytest.approx(30.00)
        assert float(sale.total_cost) == pytest.approx(30.00)
        assert float(sale.profit) == pytest.approx(0.00)
