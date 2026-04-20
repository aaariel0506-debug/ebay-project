"""
tests/test_order_sync_service.py

Day 26: OrderSyncService 测试
"""

from contextlib import contextmanager
from datetime import datetime
from decimal import Decimal
from itertools import cycle
from unittest.mock import MagicMock

from core.models import Order, OrderItem, OrderStatus, Transaction, TransactionType
from modules.finance.order_sync_service import (
    OrderSyncService,
    _decimal,
    _parse_order_status,
)


class TestHelpers:
    """解析辅助函数测试"""

    def test_decimal_from_string(self):
        assert _decimal("123.45") == Decimal("123.45")

    def test_decimal_from_float(self):
        assert _decimal(99.99) == Decimal("99.99")

    def test_decimal_from_none(self):
        assert _decimal(None) == Decimal("0")

    def test_decimal_from_invalid(self):
        assert _decimal("invalid") == Decimal("0")

    def test_parse_order_status_completed(self):
        assert _parse_order_status("COMPLETED") == OrderStatus.SHIPPED

    def test_parse_order_status_cancelled(self):
        assert _parse_order_status("CANCELLED") == OrderStatus.CANCELLED

    def test_parse_order_status_none(self):
        assert _parse_order_status(None) == OrderStatus.PENDING


class TestOrderSyncService:
    """OrderSyncService 测试"""

    @contextmanager
    def _patched_db_session(self, db_session):
        """
        让 sync_orders 使用 db_session 而非独立 session。

        patch get_session 直接返回 db_session，
        同时把 db_session.commit 替换为 no-op，
        由 db_session fixture 的 transaction rollback 统一清理。
        """
        import core.database.connection as conn_module

        orig_get = conn_module.get_session
        orig_commit = db_session.commit

        db_session.commit = lambda *a, **k: None

        def fake_get():
            return db_session

        conn_module.get_session = fake_get
        try:
            yield
        finally:
            conn_module.get_session = orig_get
            db_session.commit = orig_commit

    def _mock_client(self, pages: list[dict], *, repeat: bool = False) -> MagicMock:
        """
        构造 mock EbayClient。

        拦截 /sell/finances/ 路径返回空响应，
        避免 _extract_fee_from_order 的 fallback 消耗 mock 数据。
        """
        client = MagicMock()
        pages_iter = cycle(pages) if repeat else iter(pages)

        def fake_get(path: str, **kwargs):
            if "finances" in path:
                return {"transactions": []}
            return next(pages_iter)

        client.get.side_effect = fake_get
        return client

    def _clean_orders(self, db_session):
        """清理 Order 和 Transaction 表，防止跨测试数据污染"""
        db_session.query(Transaction).delete()
        db_session.query(Order).delete()
        db_session.commit()

    def test_sync_single_page_one_order(self, db_session, sample_product):
        """单页单条订单 → Order + Transaction 写入"""
        self._clean_orders(db_session)
        api_data = {
            "orders": [
                {
                    "orderId": "ORD-TEST-001",
                    "creationDate": "2026-04-15T10:00:00Z",
                    "orderFulfillmentStatus": {"status": "COMPLETED"},
                    "buyerCountry": "US",
                    "shippingAddress": {
                        "recipient": "John Doe",
                        "country": "US",
                    },
                    "fulfillmentHrefs": [],
                    "lineItems": [
                        {
                            "sku": sample_product.sku,
                            "quantity": 2,
                            "lineItemCost": {"currency": "USD", "value": "50.00"},
                        }
                    ],
                    "itemTxSummaries": [],
                }
            ],
        }

        client = self._mock_client([api_data])
        svc = OrderSyncService(client=client)

        with self._patched_db_session(db_session):
            result = svc.sync_orders(
                date_from=datetime(2026, 4, 1),
                date_to=datetime(2026, 4, 20),
            )

        assert result.total_orders == 1
        assert result.upserted == 1
        assert result.skipped == 0
        assert len(result.errors) == 0

        order = db_session.query(Order).filter(
            Order.ebay_order_id == "ORD-TEST-001"
        ).first()
        assert order is not None
        # Order.sku 已移至 OrderItem
        order_item = db_session.query(OrderItem).filter(
            OrderItem.order_id == "ORD-TEST-001",
            OrderItem.sku == sample_product.sku,
        ).first()
        assert order_item is not None
        assert order_item.quantity == 2
        assert order_item.sale_amount == float(Decimal("100.00"))

        assert order.sale_price == Decimal("100.00")
        assert order.status == OrderStatus.SHIPPED
        assert order.buyer_country == "US"

        tx_sale = db_session.query(Transaction).filter(
            Transaction.order_id == "ORD-TEST-001",
            Transaction.type == TransactionType.SALE,
        ).first()
        assert tx_sale is not None
        assert tx_sale.amount == 100.0
        # CostLinker：unit_cost 来自 Product.cost_price，total_cost = unit_cost * qty
        assert tx_sale.unit_cost == float(sample_product.cost_price)  # 100.0
        assert tx_sale.total_cost == float(sample_product.cost_price * 2)  # 200.0
        assert tx_sale.profit == 100.0 - float(sample_product.cost_price * 2)  # -100.0
        assert tx_sale.margin is not None

    def test_sync_with_fee(self, db_session, sample_product):
        """带 FEE 的订单 → Transaction 有 FEE 记录"""
        api_data = {
            "orders": [
                {
                    "orderId": "ORD-FEE-001",
                    "creationDate": "2026-04-15T10:00:00Z",
                    "orderFulfillmentStatus": {"status": "COMPLETED"},
                    "buyerCountry": "US",
                    "shippingAddress": {},
                    "fulfillmentHrefs": [],
                    "lineItems": [
                        {
                            "sku": sample_product.sku,
                            "quantity": 1,
                            "lineItemCost": {"currency": "USD", "value": "100.00"},
                            "itemTxSummaries": [
                                {
                                    "transactionType": "FEE",
                                    "amount": {"currency": "USD", "value": "13.00"},
                                }
                            ],
                        }
                    ],
                }
            ],
        }

        client = self._mock_client([api_data])
        svc = OrderSyncService(client=client)

        with self._patched_db_session(db_session):
            result = svc.sync_orders(
                date_from=datetime(2026, 4, 1),
                date_to=datetime(2026, 4, 20),
            )

        assert result.upserted == 1

        tx_fee = db_session.query(Transaction).filter(
            Transaction.order_id == "ORD-FEE-001",
            Transaction.type == TransactionType.FEE,
        ).first()
        assert tx_fee is not None
        assert tx_fee.amount == -13.0

    def test_sync_idempotent_order_written_once(self, db_session, sample_product):
        """
        幂等性验证：同一订单只产生一条 DB 记录（update 而非重复 insert）。
        """
        api_data = {
            "orders": [
                {
                    "orderId": "ORD-IDEM-001",
                    "creationDate": "2026-04-15T10:00:00Z",
                    "orderFulfillmentStatus": {"status": "COMPLETED"},
                    "buyerCountry": "US",
                    "shippingAddress": {},
                    "lineItems": [
                        {
                            "sku": sample_product.sku,
                            "quantity": 3,
                            "lineItemCost": {"currency": "USD", "value": "20.00"},
                            "itemTxSummaries": [
                                {
                                    "transactionType": "FEE",
                                    "amount": {"currency": "USD", "value": "5.00"},
                                }
                            ],
                        }
                    ],
                    "fulfillmentHrefs": [
                        {"shippingCost": {"currency": "USD", "value": "3.00"}}
                    ],
                }
            ],
        }

        client = self._mock_client([api_data], repeat=True)
        svc = OrderSyncService(client=client)

        with self._patched_db_session(db_session):
            r1 = svc.sync_orders(datetime(2026, 4, 1), datetime(2026, 4, 20))
            assert r1.upserted == 1

            # 第二次 sync：Order 已存在走 update，但 Transaction 幂等检查各自通过
            r2 = svc.sync_orders(datetime(2026, 4, 1), datetime(2026, 4, 20))
            assert r2.upserted == 1  # update 不报错

            # Transaction：每种 type 各自只有一条（幂等）
            for t in [TransactionType.SALE, TransactionType.SHIPPING, TransactionType.FEE]:
                cnt = db_session.query(Transaction).filter(
                    Transaction.order_id == "ORD-IDEM-001",
                    Transaction.sku == sample_product.sku,
                    Transaction.type == t,
                ).count()
                assert cnt == 1, f"{t.value} 应只有 1 条，实际 {cnt}"

        # Order 记录也只有 1 条
        count = db_session.query(Order).filter(
            Order.ebay_order_id == "ORD-IDEM-001"
        ).count()
        assert count == 1, "同一订单不应产生重复记录"

    def test_sync_order_without_line_items_skipped(self, db_session):
        """订单无 lineItems → 跳过"""
        api_data = {
            "orders": [
                {
                    "orderId": "ORD-EMPTY-001",
                    "creationDate": "2026-04-15T10:00:00Z",
                    "lineItems": [],
                }
            ],
        }

        client = self._mock_client([api_data])
        svc = OrderSyncService(client=client)

        with self._patched_db_session(db_session):
            result = svc.sync_orders(datetime(2026, 4, 1), datetime(2026, 4, 20))

        assert result.total_orders == 1
        assert result.skipped == 1
        assert result.upserted == 0

    def test_sync_multiple_pages(self, db_session, sample_product):
        """多页分页：第二页有 next link → 继续拉完"""
        page1 = {
            "orders": [
                {
                    "orderId": "ORD-PAGE1-001",
                    "creationDate": "2026-04-15T10:00:00Z",
                    "orderFulfillmentStatus": {"status": "COMPLETED"},
                    "buyerCountry": "US",
                    "shippingAddress": {},
                    "fulfillmentHrefs": [],
                    "lineItems": [
                        {
                            "sku": sample_product.sku,
                            "quantity": 1,
                            "lineItemCost": {"currency": "USD", "value": "10.00"},
                        }
                    ],
                    "itemTxSummaries": [],
                }
            ],
            "next": (
                "https://api.ebay.com/sell/fulfillment/v1/order"
                "?continuation_token=tok123"
            ),
        }
        page2 = {
            "orders": [
                {
                    "orderId": "ORD-PAGE2-001",
                    "creationDate": "2026-04-16T10:00:00Z",
                    "orderFulfillmentStatus": {"status": "COMPLETED"},
                    "buyerCountry": "JP",
                    "shippingAddress": {},
                    "fulfillmentHrefs": [],
                    "lineItems": [
                        {
                            "sku": sample_product.sku,
                            "quantity": 2,
                            "lineItemCost": {"currency": "USD", "value": "20.00"},
                        }
                    ],
                    "itemTxSummaries": [],
                }
            ],
        }

        client = self._mock_client([page1, page2])
        svc = OrderSyncService(client=client)

        with self._patched_db_session(db_session):
            result = svc.sync_orders(datetime(2026, 4, 1), datetime(2026, 4, 20))

        assert result.total_orders == 2
        assert result.total_pages == 2
        assert result.upserted == 2

        order2 = db_session.query(Order).filter(
            Order.ebay_order_id == "ORD-PAGE2-001"
        ).first()
        assert order2 is not None
        assert order2.sale_price == Decimal("40.00")

    # ── Day 26.5 重构前锁定的 bug ────────────────────────────────────────
    def test_multi_sku_order_preserves_both_line_items(
        self, db_session, sample_product
    ):
        """
        一笔订单含 2 个不同 SKU 的 line_items,两者的销售数据必须都被保留。

        当前 bug 复现:_upsert_order 循环第二个 line_item 时,
        existing = sess.query(Order).filter(ebay_order_id=X).first() 拿到
        前一轮创建的 Order;update 分支覆盖 sale_price/shipping/fee/status,
        但不更新 sku → Order 表 1 条,sku 保留第一个,sale_price 被覆盖为
        第二个 line_item 的金额。sku 与 sale_price 错配。
        Transaction 层因 (order_id, sku, type) 独立去重未受影响,
        但 Order 层损坏。

        守恒不变式(Day 26.5 重构后必须全部成立):
        - sum(Transaction.SALE.amount for same order_id) == 110.0
        - sum(Order.sale_price for same ebay_order_id) == 110.0
          ↑ 复合 PK 方案:2 条 Order,各 50/60,sum=110
          ↑ OrderItem 子表方案:1 条 Order,sale_price=订单总额=110
          ↑ 当前 bug:1 条 Order,sale_price=60,sum=60 → 失败
        """
        self._clean_orders(db_session)

        # 第二个 product(SKU-A 已由 sample_product fixture 创建)
        from core.models import Product, ProductStatus
        prod_b = Product(
            sku="TEST-SKU-002",
            title="Test Product B",
            cost_price=Decimal("20.00"),
            cost_currency="JPY",
            status=ProductStatus.ACTIVE,
            supplier="Test Supplier",
        )
        db_session.add(prod_b)
        db_session.commit()

        api_data = {
            "orders": [
                {
                    "orderId": "ORD-MULTI-001",
                    "creationDate": "2026-04-15T10:00:00Z",
                    "orderFulfillmentStatus": {"status": "COMPLETED"},
                    "buyerCountry": "US",
                    "shippingAddress": {
                        "recipient": "Multi SKU Buyer",
                        "country": "US",
                    },
                    "fulfillmentHrefs": [],
                    "lineItems": [
                        {
                            "sku": sample_product.sku,  # SKU-A
                            "quantity": 1,
                            "lineItemCost": {
                                "currency": "USD",
                                "value": "50.00",
                            },
                        },
                        {
                            "sku": prod_b.sku,  # SKU-B
                            "quantity": 2,
                            "lineItemCost": {
                                "currency": "USD",
                                "value": "30.00",
                            },
                        },
                    ],
                    "itemTxSummaries": [],
                }
            ],
        }

        client = self._mock_client([api_data])
        svc = OrderSyncService(client=client)

        with self._patched_db_session(db_session):
            svc.sync_orders(
                date_from=datetime(2026, 4, 1),
                date_to=datetime(2026, 4, 20),
            )

        # ── 不变式 1:Transaction 层 SALE 完整(当前已成立,回归保护)──
        sale_txns = db_session.query(Transaction).filter(
            Transaction.order_id == "ORD-MULTI-001",
            Transaction.type == TransactionType.SALE,
        ).all()
        assert len(sale_txns) == 2, (
            f"应有 2 条 SALE Transaction,实际 {len(sale_txns)}"
        )
        sale_by_sku = {t.sku: float(t.amount) for t in sale_txns}
        assert sale_by_sku == {
            sample_product.sku: 50.0,
            prod_b.sku: 60.0,
        }, f"Tx SALE (sku→amount) 应为 {{A:50, B:60}},实际 {sale_by_sku}"

        # ── 不变式 2:Order 层销售额守恒(当前 bug → 必失败)──
        # 两种重构方案下都应满足:Order 侧查询结果的 sale_price 合计 == 110
        #   - 复合 PK 方案:Order 表 2 条,各 50/60,sum=110 ✓
        #   - OrderItem 子表方案:Order 表 1 条,sale_price=总额 110,sum=110 ✓
        #   - 当前单 PK bug:Order 1 条,sale_price=60,sum=60 ✗
        order_rows = db_session.query(Order).filter(
            Order.ebay_order_id == "ORD-MULTI-001"
        ).all()
        order_total = sum(float(o.sale_price) for o in order_rows)
        assert order_total == 110.0, (
            f"Order 层销售总额应 == 110.0 (50+60),实际 {order_total}。"
            f"当前 bug:第二个 line_item 的 sale_price 覆盖了第一个。"
        )
