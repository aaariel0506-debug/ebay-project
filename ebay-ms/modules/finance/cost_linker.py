"""
modules/finance/cost_linker.py

Day 27: CostLinker — 把 Transaction.unit_cost / profit / margin 填满

两种场景：
1. sync 时 link（已实装）：OrderSyncService 在 sync_orders 时从 Product.cost_price 填充
2. 补填历史（link-costs）：找到 unit_cost IS NULL 的 SALE Transaction，
   用 Product.cost_price 回填（适合历史订单在 Product.cost_price 建立前的数据）

输出：
- link-costs：影响多少条，输出 .xlsx 报告
- unlinked-orders：列出仍无法关联的 Order（SKU 在 Product 表不存在）
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from core.database.connection import get_session
from core.models import Product, Transaction, TransactionType
from loguru import logger as log


@dataclass
class CostLinkResult:
    """成本关联结果。"""
    examined: int          # 检查的 Transaction 数量
    updated: int           # 实际更新的数量
    remaining: int         # 仍未关联的数量（SKU 无 cost_price）
    unlinked_skus: list[str]  # 无法关联的 SKU 列表

    def summary(self) -> str:
        return (
            f"成本关联完成：检查 {self.examined} 条 / "
            f"更新 {self.updated} 条 / "
            f"剩余 {self.remaining} 条未关联 / "
            f"未关联 SKU: {self.unlinked_skus}"
        )


def link_costs(
    dry_run: bool = True,
    since: datetime | None = None,
) -> CostLinkResult:
    """
    把 unit_cost IS NULL 的 SALE Transaction 补填成本。

    Args:
        dry_run: True 则只报告不写入
        since: 可选，只处理该时间之后创建的 Transaction（date 字段）
    """
    examined = 0
    updated = 0
    unlinked_skus: list[str] = []
    seen_unlinked: set[str] = set()

    with get_session() as sess:
        q = sess.query(Transaction).filter(
            Transaction.type == TransactionType.SALE,
            Transaction.unit_cost.is_(None),
        )
        if since:
            q = q.filter(Transaction.date >= since)

        for tx in q.all():
            examined += 1
            if tx.sku is None:
                continue

            product = sess.query(Product).filter(Product.sku == tx.sku).first()
            if product is None or product.cost_price is None:
                if tx.sku not in seen_unlinked:
                    unlinked_skus.append(tx.sku)
                    seen_unlinked.add(tx.sku)
                continue

            unit_cost = float(product.cost_price)

            if not dry_run:
                tx.unit_cost = unit_cost
                sess.add(tx)
            updated += 1  # 所有找到 cost_price 的行（dry_run 时计数不写入）

        if not dry_run:
            sess.commit()

    return CostLinkResult(
        examined=examined,
        updated=updated,
        remaining=len(unlinked_skus),
        unlinked_skus=unlinked_skus,
    )


def list_unlinked_orders(
    since: datetime | None = None,
) -> list[dict]:
    """
    列出 unit_cost IS NULL 且 type == SALE 的 Transaction 对应订单。

    Returns:
        list of dict，含 order_id, sku, amount, date
    """
    with get_session() as sess:
        q = sess.query(Transaction).filter(
            Transaction.type == TransactionType.SALE,
            Transaction.unit_cost.is_(None),
        )
        if since:
            q = q.filter(Transaction.date >= since)

        rows = q.all()
        return [
            {
                "order_id": tx.order_id,
                "sku": tx.sku,
                "amount": tx.amount,
                "currency": tx.currency,
                "date": tx.date.isoformat() if tx.date else None,
            }
            for tx in rows
            if tx.order_id
        ]


def export_unlinked_xlsx(path: Path | str, since: datetime | None = None) -> int:
    """
    把无法关联成本的订单导出为 .xlsx。
    """
    try:
        import openpyxl
    except ImportError:
        log.error("openpyxl 未安装，无法导出 xlsx")
        return 0

    records = list_unlinked_orders(since=since)
    if not records:
        log.info("没有 unlinked 订单需要导出")
        return 0

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Unlinked Orders"

    headers = ["Order ID", "SKU", "Amount", "Currency", "Date"]
    ws.append(headers)

    for r in records:
        ws.append([r["order_id"], r["sku"], r["amount"], r["currency"], r["date"]])

    wb.save(str(path))
    log.info(f"已导出 {len(records)} 条到 {path}")
    return len(records)
