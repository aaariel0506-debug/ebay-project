"""
modules/finance/amazon_cost_importer.py

从 Amazon 注文履歴 CSV 导入进货成本到 Product.cost_price。

数据流见 brief-product-import-amazon-costs-v2.md §4.1
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Optional

import pandas as pd
from core.database.connection import get_session
from core.models import Product, SupplierPriceHistory
from core.utils.asin import clean_amazon_csv_asin, is_standard_asin
from loguru import logger as log
from sqlalchemy import select

# CSV 列名（集中定义，以后 Amazon 改格式只需改这里）
# 注意：真实 CSV 列名是 "商品の小計（税込）"（不是 brief 里的 "小合計"）
_COL_ASIN = "ASIN"
_COL_ORDER_DATE = "注文日"
_COL_QTY = "注文の数量"
_COL_AMOUNT_INC = "商品の小計（税込）"   # 税込み単価の合計
_COL_AMOUNT_EXC = "商品の小計（税抜）"   # 税抜き（退税 brief 用，暂存不用）
_COL_TITLE = "商品名"


@dataclass
class AmazonCostImportResult:
    """导入结果统计。CSV 路径、各路由计数、各路由金额（用于报表）。"""
    csv_path: str = ""
    rows_total: int = 0
    rows_zero_qty: int = 0
    asin_aggregated: int = 0   # 去重后的 ASIN 数

    # 路由计数
    cost_upserted: int = 0
    ambiguous: int = 0
    unmapped: int = 0
    non_amazon: int = 0

    # 输出文件路径
    ambiguous_csv: Optional[Path] = None
    unmapped_csv: Optional[Path] = None
    non_amazon_csv: Optional[Path] = None
    summary_txt: Optional[Path] = None

    # 金额维度（JPY 税込）
    total_amount_jpy: Decimal = Decimal("0")
    upserted_amount_jpy: Decimal = Decimal("0")
    ambiguous_amount_jpy: Decimal = Decimal("0")
    unmapped_amount_jpy: Decimal = Decimal("0")
    non_amazon_amount_jpy: Decimal = Decimal("0")

    def summary(self) -> str:
        return (
            f"=== import-amazon-costs 完成 ===\n"
            f"CSV: {self.csv_path}\n"
            f"原始行数: {self.rows_total}（qty=0 跳过 {self.rows_zero_qty}）\n"
            f"去重 ASIN: {self.asin_aggregated}\n"
            f"\n--- 按 ASIN 路由 ---\n"
            f" ✅ 自动入库 cost: {self.cost_upserted} 个\n"
            f" ⚠️ 多 SKU 共享 → ambiguous_costs.csv: {self.ambiguous} 个\n"
            f" ⚠️ 未匹配 SKU → unmapped_asins.csv: {self.unmapped} 个\n"
            f" ⚠️ 非 Amazon ASIN → non_amazon_costs.csv: {self.non_amazon} 个\n"
            f"\n--- 按金额（税込 JPY）---\n"
            f" 总进货: {self.total_amount_jpy:,.0f}円\n"
            f" 自动入库: {self.upserted_amount_jpy:,.0f}円\n"
            f" ambiguous: {self.ambiguous_amount_jpy:,.0f}円\n"
            f" unmapped: {self.unmapped_amount_jpy:,.0f}円\n"
            f" non_amazon: {self.non_amazon_amount_jpy:,.0f}円\n"
        )


class AmazonCostImporter:
    SUPPLIER_DEFAULT = "Amazon JP"
    OUTPUT_DIR = Path.home() / ".ebay-project" / "imports"

    def __init__(self, *, output_dir: Optional[Path] = None):
        self.output_dir = output_dir or self.OUTPUT_DIR
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def import_csv(self, csv_path: Path) -> AmazonCostImportResult:
        result = AmazonCostImportResult(csv_path=str(csv_path))

        try:
            df = pd.read_csv(csv_path, encoding="utf-8")
        except FileNotFoundError:
            raise RuntimeError(f"CSV 文件不存在: {csv_path}")
        except UnicodeDecodeError:
            raise RuntimeError(f"CSV 编码错误（预期 UTF-8）: {csv_path}")

        result.rows_total = len(df)

        # 验证必要列存在
        missing = [
            c for c in [_COL_ASIN, _COL_QTY, _COL_AMOUNT_INC]
            if c not in df.columns
        ]
        if missing:
            raise RuntimeError(f"CSV 缺少必要列: {missing}，实际列: {list(df.columns[:10])}...")

        # 清洗 ASIN（剥 ="..." 外壳）
        df["asin_clean"] = df[_COL_ASIN].apply(clean_amazon_csv_asin)

        # 剔除 qty=0 / 缺失 qty（退货行）
        zero_mask = pd.to_numeric(df[_COL_QTY], errors="coerce").fillna(0).astype(int) <= 0
        result.rows_zero_qty = int(zero_mask.sum())
        df = df[~zero_mask].copy()

        if df.empty:
            result.asin_aggregated = 0
            log.warning("CSV 没有有效数据行（全部 qty=0）")
            return result

        # 按 ASIN 聚合（税込み）
        df["amount_inc"] = pd.to_numeric(df[_COL_AMOUNT_INC], errors="coerce").fillna(0)
        agg = df.groupby("asin_clean").agg(
            qty=(_COL_QTY, "sum"),
            amount_inc=("amount_inc", "sum"),
            order_date_latest=(_COL_ORDER_DATE, "max"),
            title=(_COL_TITLE, "first"),
        ).reset_index()
        result.asin_aggregated = len(agg)

        # 路由
        ambiguous_rows: list[dict] = []
        unmapped_rows: list[dict] = []
        non_amazon_rows: list[dict] = []

        with get_session() as sess:
            # 一次性把所有有 asin 的 product 拉出来，按 asin 索引
            products_by_asin: dict[str, list[Product]] = {}
            for p in sess.execute(
                select(Product).where(Product.asin.isnot(None))
            ).scalars():
                products_by_asin.setdefault(p.asin, []).append(p)

            for _, r in agg.iterrows():
                asin: str = r["asin_clean"]
                amount = Decimal(str(r["amount_inc"]))
                qty = int(r["qty"])
                title = str(r.get("title", ""))[:120]
                row_summary = {
                    "asin": asin,
                    "qty": qty,
                    "amount_jpy": float(amount),
                    "title": title,
                    "order_date_latest": str(r["order_date_latest"]),
                }

                result.total_amount_jpy += amount

                # 路由 1: 非标准 ASIN（ISBN/JAN/其他）
                if not is_standard_asin(asin):
                    non_amazon_rows.append(row_summary)
                    result.non_amazon += 1
                    result.non_amazon_amount_jpy += amount
                    continue

                # 路由 2: 按 products 表里的 SKU 数路由
                matched = products_by_asin.get(asin, [])
                if len(matched) == 0:
                    unmapped_rows.append(row_summary)
                    result.unmapped += 1
                    result.unmapped_amount_jpy += amount
                elif len(matched) > 1:
                    row_summary["sku_candidates"] = ";".join(p.sku for p in matched)
                    ambiguous_rows.append(row_summary)
                    result.ambiguous += 1
                    result.ambiguous_amount_jpy += amount
                else:
                    p = matched[0]
                    new_cost = (amount / qty).quantize(Decimal("0.01"))

                    # D3: 旧 cost_price 非 NULL 时记历史
                    if p.cost_price is not None:
                        sess.add(SupplierPriceHistory(
                            sku=p.sku,
                            supplier=p.supplier,
                            price=p.cost_price,
                            currency=p.cost_currency or "JPY",
                            recorded_at=date.today(),
                            note="superseded by import-amazon-costs",
                        ))

                    p.cost_price = new_cost
                    p.cost_currency = "JPY"
                    p.supplier = self.SUPPLIER_DEFAULT
                    # source_url 不动（Brief 1 已填）

                    result.cost_upserted += 1
                    result.upserted_amount_jpy += amount

                # 小延迟，防 DB 锁
                time.sleep(0.01)

        # 输出报告
        result.ambiguous_csv = self._write_csv("ambiguous_costs.csv", ambiguous_rows)
        result.unmapped_csv = self._write_csv("unmapped_asins.csv", unmapped_rows)
        result.non_amazon_csv = self._write_csv("non_amazon_costs.csv", non_amazon_rows)
        result.summary_txt = self._write_summary(result)

        return result

    def _write_csv(self, name: str, rows: list[dict]) -> Path:
        path = self.output_dir / name
        if rows:
            pd.DataFrame(rows).to_csv(path, index=False, encoding="utf-8")
        else:
            # 即使空也建文件，留个 header，业务侧打开看到"今天没东西"
            path.write_text("# (empty - 本次导入此分类无记录)\n", encoding="utf-8")
        return path

    def _write_summary(self, result: AmazonCostImportResult) -> Path:
        path = self.output_dir / "import_summary.txt"
        path.write_text(result.summary(), encoding="utf-8")
        return path
