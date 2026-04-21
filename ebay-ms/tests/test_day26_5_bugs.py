"""
tests/test_day26_5_bugs.py

Day 26.5 代码审查发现的 4 个 bug 及其修复验收。

历史:
- eafa730(首版审查):4 个 bug 都锁 xfail(strict=True),均未修
- 6e94c52(UM870 回炉):Bug 1、2、4 的生产代码修了;Bug 3 没真修
  (UM870 用自写的玩具测试模拟"修完后的 SQL",没实际改 migration)
- 本提交:补修 migration downgrade(Bug 3),4 个测试全部移除 xfail 装饰器
  并通过

4 个测试现在全部通过。若回归失败,说明对应 bug 复发。
"""

from __future__ import annotations

import os
import subprocess
import sys
from contextlib import contextmanager
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from core.models import (
    Order,
    OrderItem,
    Product,
    ProductStatus,
    Transaction,
    TransactionType,
)
from modules.finance.order_sync_service import OrderSyncService
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

# ─── 共用 helper(从 test_order_sync_service.py 抽的精简版)────────────────


@contextmanager
def _patched_db_session(db_session):
    """让 sync_orders 用 db_session,避免事务提交污染其他测试"""
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


def _mock_client(api_data: dict) -> MagicMock:
    """mock EbayClient,finances 路径返回空"""
    client = MagicMock()

    def fake_get(path: str, **kwargs):
        if "finances" in path:
            return {"transactions": []}
        return api_data

    client.get.side_effect = fake_get
    return client


def _clean(db_session):
    db_session.query(Transaction).delete()
    db_session.query(OrderItem).delete()
    db_session.query(Order).delete()
    db_session.commit()


# ─── Bug 1:多 SKU 订单 FEE/SHIPPING 重复记账 ─────────────────────────────


# Day 26.5 二次回炉已修复(commit 6e94c52):FEE/SHIPPING 写入已拆成
# _write_fee_transaction / _write_shipping_transaction 两个方法,在 line_item
# 循环外 per-order 调用一次,sku=NULL。
def test_bug1_multi_sku_fee_shipping_not_duplicated(db_session):
    """
    多 SKU 订单 ORD-B1 含 SKU-B1A + SKU-B1B,订单级 fee=10, shipping=5。

    守恒断言:
    - sum(Transaction.FEE.amount for order_id) == -Order.ebay_fee
    - sum(Transaction.SHIPPING.amount for order_id) == Order.shipping_cost
    """
    _clean(db_session)

    # 两个 product
    for sku in ["SKU-B1A", "SKU-B1B"]:
        db_session.add(Product(
            sku=sku,
            title=f"Bug1 Product {sku}",
            cost_price=Decimal("10.00"),
            cost_currency="USD",
            status=ProductStatus.ACTIVE,
            supplier="T",
        ))
    db_session.commit()

    api_data = {
        "orders": [{
            "orderId": "ORD-B1",
            "creationDate": "2026-04-15T10:00:00Z",
            "orderFulfillmentStatus": {"status": "COMPLETED"},
            "buyerCountry": "US",
            "shippingAddress": {"country": "US"},
            # 订单级 shipping = 5
            "fulfillmentHrefs": [
                {"shippingCost": {"value": "5.00", "currency": "USD"}}
            ],
            "lineItems": [
                {
                    "sku": "SKU-B1A",
                    "quantity": 1,
                    "lineItemCost": {"currency": "USD", "value": "50.00"},
                    # 订单级 fee = 10,挂在第一个 line_item 的 itemTxSummaries 下
                    "itemTxSummaries": [
                        {"transactionType": "FEE", "amount": {"value": "10.00"}}
                    ],
                },
                {
                    "sku": "SKU-B1B",
                    "quantity": 1,
                    "lineItemCost": {"currency": "USD", "value": "30.00"},
                    "itemTxSummaries": [],
                },
            ],
        }]
    }

    svc = OrderSyncService(client=_mock_client(api_data))
    with _patched_db_session(db_session):
        svc.sync_orders(
            date_from=datetime(2026, 4, 1),
            date_to=datetime(2026, 4, 20),
        )

    order = db_session.query(Order).filter(
        Order.ebay_order_id == "ORD-B1"
    ).first()
    assert order is not None, "Order ORD-B1 应该被创建"

    fee_sum = sum(
        float(t.amount)
        for t in db_session.query(Transaction).filter(
            Transaction.order_id == "ORD-B1",
            Transaction.type == TransactionType.FEE,
        ).all()
    )
    shipping_sum = sum(
        float(t.amount)
        for t in db_session.query(Transaction).filter(
            Transaction.order_id == "ORD-B1",
            Transaction.type == TransactionType.SHIPPING,
        ).all()
    )

    # FEE 守恒:Transaction 里 FEE 是负数,abs(sum) == Order.ebay_fee
    assert fee_sum == -float(order.ebay_fee), (
        f"FEE 守恒失败:sum(Transaction.FEE)={fee_sum} "
        f"应 == -Order.ebay_fee={-float(order.ebay_fee)}。"
        f"当前 bug:订单级 fee 被按 SKU 重复写 N 倍。"
    )
    # SHIPPING 守恒
    assert shipping_sum == float(order.shipping_cost), (
        f"SHIPPING 守恒失败:sum(Transaction.SHIPPING)={shipping_sum} "
        f"应 == Order.shipping_cost={float(order.shipping_cost)}。"
        f"当前 bug:订单级 shipping 被按 SKU 重复写 N 倍。"
    )


# ─── Bug 2:upgrade 后 orders 表失去 PRIMARY KEY ───────────────────────────


# Day 26.5 二次回炉已修复(commit 6e94c52):upgrade 里 orders_new 改为显式
# CREATE TABLE ... ebay_order_id VARCHAR(64) NOT NULL PRIMARY KEY(不再用
# CREATE TABLE AS SELECT)。
def test_bug2_upgrade_orders_retains_primary_key(db_session):
    """
    conftest 已经 alembic upgrade head,直接查 sqlite_master 看 orders
    表的 CREATE TABLE 语句是否含 PRIMARY KEY 约束。
    """
    row = db_session.execute(
        text("SELECT sql FROM sqlite_master WHERE type='table' AND name='orders'")
    ).fetchone()
    assert row is not None, "orders 表应存在"
    schema_sql = row[0].upper()

    # 主键约束:可能以 "PRIMARY KEY(X)" 或 "X ... PRIMARY KEY" 出现
    has_pk = "PRIMARY KEY" in schema_sql
    assert has_pk, (
        f"upgrade 后 orders 表应含 PRIMARY KEY 约束。实际 schema:\n{row[0]}"
    )

    # 进一步:ebay_order_id 应该是 NOT NULL(因为是 PK)
    # 在 CREATE TABLE AS SELECT 的坏实现下,所有列都是 nullable
    # 这里用 PRAGMA 更准确
    cols = db_session.execute(text("PRAGMA table_info(orders)")).fetchall()
    ebay_order_id_col = [c for c in cols if c[1] == "ebay_order_id"]
    assert len(ebay_order_id_col) == 1, "orders 表应有 ebay_order_id 列"
    col = ebay_order_id_col[0]
    # PRAGMA table_info 返回 (cid, name, type, notnull, dflt_value, pk)
    notnull = col[3]
    pk = col[5]
    assert pk == 1, (
        f"ebay_order_id 应是 PRIMARY KEY(pk 标志 == 1),实际 pk={pk}。"
        f"schema:\n{row[0]}"
    )
    assert notnull == 1, (
        f"ebay_order_id 应是 NOT NULL,实际 notnull={notnull}。"
        f"schema:\n{row[0]}"
    )


# ─── Bug 3:downgrade 销毁 orders 数据 ─────────────────────────────────────


# ─── Bug 3:downgrade 销毁 orders 数据 ─────────────────────────────────────


# Day 26.5 二次回炉已修复:downgrade 改为在建完新 orders 表后先
# INSERT INTO orders SELECT ... FROM orders_old 把所有订单级字段回填,
# 然后再 UPDATE 从 order_items 回填 sku。sku 列改为 nullable(容忍
# 极端情况下 order_items 无对应记录)。
def test_bug3_downgrade_preserves_order_level_fields(tmp_path):
    """
    在独立 tmp SQLite 上跑 upgrade head → 插真实数据 → downgrade -1 →
    断言订单级字段仍然保留。

    用 subprocess 起独立进程 + DB_DIR/DB_NAME 环境变量覆盖 settings。
    """
    project_root = Path(__file__).parent.parent  # ebay-ms/
    db_dir = tmp_path
    db_name = "bug3_test.db"
    db_file = db_dir / db_name

    env = {
        **os.environ,
        "DB_DIR": str(db_dir),
        "DB_NAME": db_name,
    }

    def run_alembic(*args: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            [sys.executable, "-m", "alembic", *args],
            cwd=project_root,
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )

    # 1. upgrade head
    r = run_alembic("upgrade", "head")
    assert r.returncode == 0, f"upgrade head 失败:\nstdout={r.stdout}\nstderr={r.stderr}"
    assert db_file.exists(), f"临时 DB 未创建: {db_file}"

    # 2. 在 orders 表直接插入真实订单数据(绕过 ORM)
    import sqlite3
    conn = sqlite3.connect(str(db_file))
    cur = conn.cursor()
    # products 先建(FK 要;注意 cost_price 是 NOT NULL)
    cur.execute("""
        INSERT INTO products (sku, title, status, cost_currency, cost_price,
                              created_at, updated_at)
        VALUES ('SKU-BUG3', 'Bug3 Product', 'active', 'USD', 50.00,
                CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
    """)
    # order_items(Bug 3 downgrade 从这里回填 sku)
    cur.execute("""
        INSERT INTO order_items (order_id, sku, quantity, unit_price, sale_amount,
                                 created_at, updated_at)
        VALUES ('ORD-BUG3', 'SKU-BUG3', 2, 50, 100,
                CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
    """)
    # orders(完整订单级字段)
    cur.execute("""
        INSERT INTO orders (ebay_order_id, sale_price, shipping_cost, ebay_fee,
                           buyer_country, status, buyer_name, shipping_address,
                           created_at, updated_at)
        VALUES ('ORD-BUG3', 100, 7.50, 13.00, 'JP', 'shipped',
                'Tanaka Taro', '1-1 Shibuya Tokyo',
                CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
    """)
    conn.commit()
    conn.close()

    # 3. downgrade 到 6e3d8f2a1c4d(82b6ba3706c4 之前,即撤销 OrderItem 拆分)
    # 不用 "-1" 是因为后续可能还会加新 migration,会污染测试语义
    r = run_alembic("downgrade", "6e3d8f2a1c4d")
    assert r.returncode == 0, (
        f"downgrade 失败:\nstdout={r.stdout}\nstderr={r.stderr}"
    )

    # 4. 验证订单级字段还在
    conn = sqlite3.connect(str(db_file))
    cur = conn.cursor()
    row = cur.execute("""
        SELECT sale_price, shipping_cost, ebay_fee, buyer_country, status,
               buyer_name, shipping_address, sku
        FROM orders
        WHERE ebay_order_id = 'ORD-BUG3'
    """).fetchone()
    conn.close()

    assert row is not None, "downgrade 后 ORD-BUG3 记录消失了!"
    (sale_price, shipping_cost, ebay_fee, buyer_country, status,
     buyer_name, shipping_address, sku) = row

    # 订单级字段必须保留(当前 bug:这些都变 None)
    assert sale_price == 100, f"sale_price 应 == 100,实际 {sale_price}"
    assert shipping_cost == 7.5, (
        f"shipping_cost 应 == 7.5,实际 {shipping_cost}(当前 bug: None 或 0)"
    )
    assert ebay_fee == 13.0, (
        f"ebay_fee 应 == 13.0,实际 {ebay_fee}(当前 bug: None 或 0)"
    )
    assert buyer_country == "JP", (
        f"buyer_country 应 == 'JP',实际 {buyer_country}(当前 bug: None)"
    )
    assert status == "shipped", (
        f"status 应 == 'shipped',实际 {status}"
    )
    assert buyer_name == "Tanaka Taro", (
        f"buyer_name 应保留,实际 {buyer_name}"
    )
    assert shipping_address == "1-1 Shibuya Tokyo", (
        f"shipping_address 应保留,实际 {shipping_address}"
    )
    # sku 是从 order_items 回填的
    assert sku == "SKU-BUG3", f"sku 从 order_items 回填应 == 'SKU-BUG3',实际 {sku}"


# ─── Bug 4:OrderItem 的 __table_args__ 声称有 UNIQUE 但其实是空 ───────────


# Day 26.5 二次回炉已修复(commit 6e94c52 + b8d46d8c3b34 migration):
# OrderItem 加了 UniqueConstraint("order_id", "sku", ...),独立 migration
# b8d46d8c3b34 加上了数据库层 UNIQUE 约束。
def test_bug4_orderitem_unique_constraint_on_order_id_sku(db_session):
    """
    同一 (order_id, sku) 插两条 OrderItem,第二条应因 UNIQUE 约束抛 IntegrityError。

    当前 bug:没有 UNIQUE 约束,第二条会成功插入(Python 层去重是 order_sync 的
    业务逻辑,绕过 order_sync 直连 DB 就能写脏数据)。
    """
    _clean(db_session)

    # 先建 Product + Order
    db_session.add(Product(
        sku="SKU-BUG4",
        title="Bug4 Product",
        cost_price=Decimal("10.00"),
        cost_currency="USD",
        status=ProductStatus.ACTIVE,
        supplier="T",
    ))
    db_session.add(Order(
        ebay_order_id="ORD-BUG4",
        sale_price=Decimal("50.00"),
        shipping_cost=Decimal("0"),
        ebay_fee=Decimal("0"),
    ))
    db_session.commit()

    # 第一条 OK
    db_session.add(OrderItem(
        order_id="ORD-BUG4",
        sku="SKU-BUG4",
        quantity=1,
        unit_price=Decimal("50.00"),
        sale_amount=Decimal("50.00"),
    ))
    db_session.commit()

    # 第二条同 (order_id, sku) 必须被拦
    db_session.add(OrderItem(
        order_id="ORD-BUG4",
        sku="SKU-BUG4",
        quantity=99,  # 不同数量,但 key 相同
        unit_price=Decimal("50.00"),
        sale_amount=Decimal("4950.00"),
    ))
    with pytest.raises(IntegrityError):
        db_session.commit()
