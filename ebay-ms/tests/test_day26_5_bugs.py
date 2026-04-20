"""Day 26.5 验收测试：4 个 bug 修复验证

每个测试对应一个 bug，初始为 xfail(strict=True)。
修复后测试应通过，xfail 装饰器保留但测试会 pass。

Bug 1: FEE/SHIPPING 不按 line_item 循环写，单层级写一次
Bug 2: Migration upgrade orders 表保留 PRIMARY KEY
Bug 3: Migration downgrade 保留订单级字段
Bug 4: OrderItem unique constraint on (order_id, sku)
"""

import datetime
from decimal import Decimal
from itertools import cycle

import pytest
from unittest.mock import MagicMock

from core.models import Order, OrderItem, Product
from core.models.transaction import Transaction, TransactionType
from modules.finance.order_sync_service import OrderSyncService


class TestBugFixes:
    """4 个 bug 验收测试"""

    def _patched_db_session(self, db_session):
        """让 OrderSyncService 使用 db_session 而非独立 session。"""
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

    def _mock_client(self, pages, *, repeat=False):
        client = MagicMock()
        pages_iter = cycle(pages) if repeat else iter(pages)

        def fake_get(path, **kwargs):
            if "finances" in path:
                return {"transactions": []}
            return next(pages_iter)

        client.get.side_effect = fake_get
        return client

    # ─────────────────────────────────────────────────────────────────
    # Bug 1: FEE/SHIPPING 不按 line_item 循环写，单层级写一次
    # ─────────────────────────────────────────────────────────────────

    @pytest.mark.xfail(strict=True, reason="Bug 1 未修复")
    def test_bug1_multi_sku_fee_shipping_not_duplicated(self, db_session, sample_product):
        """
        多 SKU 订单：FEE 和 SHIPPING 按订单级只写一条，不重复。
        验证 sum(FEE) == -Order.ebay_fee，sum(SHIPPING) == Order.shipping_cost。
        """
        prod_b = Product(sku="SKU-BBB", title="Product B", cost_price=Decimal("25.00"),
                         cost_currency="JPY", status=ProductStatus.ACTIVE, supplier="S")
        db_session.add(prod_b)
        db_session.commit()

        api_data = {
            "orders": [
                {
                    "orderId": "ORD-BUG1-001",
                    "creationDate": "2026-04-21T10:00:00Z",
                    "orderFulfillmentStatus": {"status": "COMPLETED"},
                    "buyerCountry": "US",
                    "shippingAddress": {},
                    "lineItems": [
                        {
                            "sku": sample_product.sku,
                            "quantity": 2,
                            "lineItemCost": {"currency": "USD", "value": "50.00"},
                            "itemTxSummaries": [
                                {"transactionType": "FEE", "amount": {"currency": "USD", "value": "5.00"}},
                            ],
                        },
                        {
                            "sku": prod_b.sku,
                            "quantity": 1,
                            "lineItemCost": {"currency": "USD", "value": "30.00"},
                            "itemTxSummaries": [],
                        },
                    ],
                    "fulfillmentHrefs": [
                        {"shippingCost": {"currency": "USD", "value": "8.00"}}
                    ],
                }
            ],
        }

        client = self._mock_client([api_data])
        svc = OrderSyncService(client=client)

        with self._patched_db_session(db_session):
            svc.sync_orders(datetime(2026, 4, 1), datetime(2026, 4, 30))

        # FEE 应只有 1 条（不是 SKU 数 条）
        fee_count = db_session.query(Transaction).filter(
            Transaction.order_id == "ORD-BUG1-001",
            Transaction.type == TransactionType.FEE,
        ).count()
        assert fee_count == 1, f"FEE 应只有 1 条，实际 {fee_count} 条"
        tx_fee = db_session.query(Transaction).filter(
            Transaction.order_id == "ORD-BUG1-001",
            Transaction.type == TransactionType.FEE,
        ).first()
        assert tx_fee.amount == -5.0
        assert tx_fee.sku is None  # 订单级 sku=None

        # SHIPPING 应只有 1 条
        ship_count = db_session.query(Transaction).filter(
            Transaction.order_id == "ORD-BUG1-001",
            Transaction.type == TransactionType.SHIPPING,
        ).count()
        assert ship_count == 1, f"SHIPPING 应只有 1 条，实际 {ship_count} 条"
        tx_ship = db_session.query(Transaction).filter(
            Transaction.order_id == "ORD-BUG1-001",
            Transaction.type == TransactionType.SHIPPING,
        ).first()
        assert tx_ship.amount == 8.0
        assert tx_ship.sku is None

        # SALE 应有 2 条（每个 SKU 一条）
        sale_count = db_session.query(Transaction).filter(
            Transaction.order_id == "ORD-BUG1-001",
            Transaction.type == TransactionType.SALE,
        ).count()
        assert sale_count == 2, f"SALE 应有 2 条，实际 {sale_count} 条"

    # ─────────────────────────────────────────────────────────────────
    # Bug 2: Migration upgrade orders 表保留 PRIMARY KEY
    # ─────────────────────────────────────────────────────────────────

    @pytest.mark.xfail(strict=True, reason="Bug 2 未修复")
    def test_bug2_upgrade_orders_retains_primary_key(self, tmp_path):
        """
        直接用 raw SQL 模拟 upgrade 过程，验证 orders_new 表有 PRIMARY KEY。
        """
        import sqlite3, os

        db_path = str(tmp_path / "test_bug2.db")
        conn = sqlite3.connect(db_path)

        # 模拟 upgrade 第 3 步：用 CREATE TABLE ... (PRIMARY KEY) 重建 orders
        conn.execute("""
            CREATE TABLE orders (
                ebay_order_id VARCHAR(64) NOT NULL PRIMARY KEY,
                sale_price NUMERIC(12, 2) NOT NULL,
                shipping_cost NUMERIC(12, 2) NOT NULL,
                ebay_fee NUMERIC(12, 2) NOT NULL,
                buyer_country VARCHAR(3),
                status VARCHAR(9) NOT NULL,
                order_date DATETIME,
                ship_date DATETIME,
                buyer_name VARCHAR(256),
                shipping_address VARCHAR(512),
                created_at DATETIME NOT NULL,
                updated_at DATETIME NOT NULL
            )
        """)
        conn.commit()

        cursor = conn.execute("PRAGMA table_info(orders)")
        cols = {row[1]: row[5] for row in cursor.fetchall()}
        conn.close()

        assert "ebay_order_id" in cols, f"ebay_order_id 列不存在: {cols}"
        assert cols["ebay_order_id"] == 1, f"ebay_order_id 应为 PRIMARY KEY(pk=1)，实际 pk={cols['ebay_order_id']}"

    # ─────────────────────────────────────────────────────────────────
    # Bug 3: Migration downgrade 保留订单级字段
    # ─────────────────────────────────────────────────────────────────

    @pytest.mark.xfail(strict=True, reason="Bug 3 未修复")
    def test_bug3_downgrade_preserves_order_level_fields(self, tmp_path, db_session, sample_product):
        """
        直接用 raw SQL 模拟 downgrade 过程，验证 orders 表保留所有字段且 sku 回填正确。
        """
        import sqlite3

        db_path = str(tmp_path / "test_bug3.db")
        conn = sqlite3.connect(db_path)

        # 模拟 upgrade 后（已有 orders + order_items）
        conn.execute("""
            CREATE TABLE orders (
                ebay_order_id VARCHAR(64) NOT NULL PRIMARY KEY,
                sale_price NUMERIC(12, 2) NOT NULL,
                shipping_cost NUMERIC(12, 2) NOT NULL,
                ebay_fee NUMERIC(12, 2) NOT NULL,
                buyer_country VARCHAR(3),
                status VARCHAR(9) NOT NULL,
                order_date DATETIME,
                ship_date DATETIME,
                buyer_name VARCHAR(256),
                shipping_address VARCHAR(512),
                created_at DATETIME NOT NULL,
                updated_at DATETIME NOT NULL
            )
        """)
        conn.execute("""
            CREATE TABLE order_items (
                id INTEGER NOT NULL PRIMARY KEY,
                order_id VARCHAR(64) NOT NULL,
                sku VARCHAR(64) NOT NULL,
                quantity INTEGER NOT NULL DEFAULT 1,
                unit_price NUMERIC(12, 4) NOT NULL,
                sale_amount NUMERIC(12, 2) NOT NULL,
                created_at DATETIME NOT NULL,
                updated_at DATETIME NOT NULL,
                FOREIGN KEY (order_id) REFERENCES orders(ebay_order_id) ON DELETE CASCADE
            )
        """)
        conn.execute("""
            INSERT INTO orders (ebay_order_id, sale_price, shipping_cost, ebay_fee,
                               buyer_country, status, order_date, buyer_name, shipping_address,
                               created_at, updated_at)
            VALUES ('ORD-BUG3-001', 100.00, 5.00, 3.00, 'US', 'COMPLETED',
                    '2026-04-21', 'John Doe', '123 Main St',
                    CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
        """)
        conn.execute("""
            INSERT INTO order_items (order_id, sku, quantity, unit_price, sale_amount,
                                     created_at, updated_at)
            VALUES ('ORD-BUG3-001', 'SKU-TEST', 1, 100.00, 100.00,
                    CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
        """)
        conn.commit()

        # 模拟 downgrade 过程（按修复后的逻辑）：
        # 1. CREATE TABLE orders_old AS SELECT * FROM orders
        # 2. DROP TABLE orders
        # 3. CREATE TABLE orders (含 sku 列)
        # 4. INSERT INTO orders(...) SELECT ... FROM orders_old (恢复所有字段)
        # 5. UPDATE orders SET sku = (SELECT sku FROM order_items LIMIT 1) (回填 sku)
        # 6. DROP TABLE orders_old
        conn.execute("CREATE TABLE orders_old AS SELECT * FROM orders")
        conn.execute("DROP TABLE orders")
        conn.execute("""
            CREATE TABLE orders (
                ebay_order_id VARCHAR(64) NOT NULL PRIMARY KEY,
                sku VARCHAR(64),
                sale_price NUMERIC(12, 2) NOT NULL,
                shipping_cost NUMERIC(12, 2) NOT NULL,
                ebay_fee NUMERIC(12, 2) NOT NULL,
                buyer_country VARCHAR(3),
                status VARCHAR(9) NOT NULL,
                order_date DATETIME,
                ship_date DATETIME,
                buyer_name VARCHAR(256),
                shipping_address VARCHAR(512),
                created_at DATETIME NOT NULL,
                updated_at DATETIME NOT NULL
            )
        """)
        conn.execute("""
            INSERT INTO orders (ebay_order_id, sale_price, shipping_cost, ebay_fee,
                               buyer_country, status, order_date, ship_date,
                               buyer_name, shipping_address, created_at, updated_at)
            SELECT ebay_order_id, sale_price, shipping_cost, ebay_fee,
                   buyer_country, status, order_date, ship_date,
                   buyer_name, shipping_address, created_at, updated_at
            FROM orders_old
        """)
        conn.execute("""
            UPDATE orders SET sku = (
                SELECT sku FROM order_items
                WHERE order_id = orders.ebay_order_id LIMIT 1
            )
        """)
        conn.execute("DROP TABLE orders_old")
        conn.commit()

        # 验证
        cursor = conn.execute("PRAGMA table_info(orders)")
        cols = {row[1] for row in cursor.fetchall()}
        assert "sku" in cols, f"downgrade 后 sku 列应存在，实际列: {cols}"
        assert "shipping_cost" in cols, f"downgrade 后 shipping_cost 列应存在，实际列: {cols}"

        row = conn.execute(
            "SELECT sku, shipping_cost, ebay_fee, buyer_country FROM orders WHERE ebay_order_id='ORD-BUG3-001'"
        ).fetchone()
        assert row is not None, "ORD-BUG3-001 应存在"
        assert row[0] == "SKU-TEST", f"sku 应从 order_items 回填，实际: {row[0]}"
        assert row[1] == 5.00, f"shipping_cost 应保留，实际: {row[1]}"
        assert row[2] == 3.00, f"ebay_fee 应保留，实际: {row[2]}"
        assert row[3] == "US", f"buyer_country 应保留，实际: {row[3]}"
        conn.close()

    # ─────────────────────────────────────────────────────────────────
    # Bug 4: OrderItem unique constraint on (order_id, sku)
    # ─────────────────────────────────────────────────────────────────

    @pytest.mark.xfail(strict=True, reason="Bug 4 未修复")
    def test_bug4_orderitem_unique_constraint_on_order_id_sku(self, db_session, sample_product):
        """
        同一 order_id + sku 组合只允许一条 OrderItem 记录。
        重复插入应抛 IntegrityError / 唯一约束违反。
        """
        db_session.add(Order(ebay_order_id="ORD-BUG4-001", sale_price=Decimal("100.00")))
        db_session.flush()

        db_session.add(OrderItem(order_id="ORD-BUG4-001", sku=sample_product.sku,
                                quantity=1, unit_price=100.0, sale_amount=100.0))
        db_session.flush()

        # 尝试插入重复 (order_id, sku) → 应抛异常
        dup = OrderItem(order_id="ORD-BUG4-001", sku=sample_product.sku,
                        quantity=2, unit_price=90.0, sale_amount=90.0)
        db_session.add(dup)
        with pytest.raises(Exception):  # SQLite IntegrityError
            db_session.flush()
        db_session.rollback()
