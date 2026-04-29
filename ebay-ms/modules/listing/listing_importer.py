"""
modules/listing/listing_importer.py
从 v2/v3 Excel listing 表预建 Product 主数据（SKU + ASIN + source_url）。
不含成本，成本在 Brief 2 由 Amazon CSV 注入。

输入：--file path1 [--file path2 ...]
输出：写入 products 表 + import_summary.txt（标准输出）
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import pandas as pd
from core.database.connection import get_session
from core.models import Product, ProductStatus
from core.utils.asin import (
    expand_short_link,
    extract_asin_from_url,
    is_short_link,
)
from loguru import logger as log
from sqlalchemy import select


@dataclass
class ImportListingsResult:
    """预建结果统计。"""
    sources_read: list[str] = field(default_factory=list)
    rows_total: int = 0
    sku_inserted: int = 0
    sku_updated: int = 0   # ASIN/URL 有变化才算更新
    sku_unchanged: int = 0
    short_links_expanded: int = 0
    short_links_failed: int = 0
    rows_no_sku: int = 0
    rows_no_url: int = 0
    rows_dup_in_source: int = 0   # 同一文件内重复 SKU
    duplicate_skus: list[str] = field(default_factory=list)

    def summary(self) -> str:
        return (
            f"=== import-listings 完成 ===\n"
            f"读取源: {self.sources_read}\n"
            f"总行数: {self.rows_total}\n"
            f"  新建 SKU: {self.sku_inserted}\n"
            f"  更新 SKU: {self.sku_updated}\n"
            f"  无变化:  {self.sku_unchanged}\n"
            f"  跳过（无 SKU）: {self.rows_no_sku}\n"
            f"  跳过（无 URL）: {self.rows_no_url}\n"
            f"短链展开: {self.short_links_expanded} 成功 / {self.short_links_failed} 失败\n"
            f"源内重复 SKU: {self.rows_dup_in_source} 条\n"
        )


class ListingImporter:
    """读取 v2/v3 Excel 表 → upsert 到 products。

    核心规则：
    1. 命令行顺序处理，先遇到已存在 SKU 则跳过（v3 优先 → v3 放命令行最前面）
    2. 同文件内重复：第一个生效，计入 rows_dup_in_source
    3. amzn.asia 短链自动展开拿 ASIN，展开失败 asin=NULL 但 SKU 仍预建
    4. SKU 已存在但 asin/source_url 有变化 → UPDATE（不动 status/cost_price/title/variant_note）
    5. SKU 已存在且无变化 → 跳过（写入 sku_unchanged）
    """

    SHEET_NAME = "利润试算表"
    HEADER_ROW = 2   # 0-indexed; pandas header=2 → row 3（1-indexed=row 3）为表头
    DROP_FIRST_DATA_ROW = True   # row 3（1-indexed=row 3）是"例子"，剔除
    EXPAND_SHORT_LINK_DELAY = 0.5   # 礼貌间隔，避免 amzn 限流

    def __init__(self, *, expand_short_links: bool = True):
        self.expand_short_links = expand_short_links

    def import_files(self, paths: list[Path]) -> ImportListingsResult:
        result = ImportListingsResult()
        # sku → row_dict; 先到先得（v3 优先 → 命令行先传 v3 则先遇到，先写入）
        all_rows: dict[str, dict] = {}

        for path in paths:
            log.info("读取 listing 表: {}", path)
            result.sources_read.append(str(path))
            df = self._read_excel(path)
            seen_in_this_file: set[str] = set()

            for _, row in df.iterrows():
                result.rows_total += 1

                sku = self._clean_str(row.get("ItemID（SKU)"))
                ec_url = self._clean_str(row.get("EC site URL"))

                if not sku:
                    result.rows_no_sku += 1
                    continue

                # 同一文件内重复：第一个生效
                if sku in seen_in_this_file:
                    result.rows_dup_in_source += 1
                    result.duplicate_skus.append(sku)
                    continue
                seen_in_this_file.add(sku)

                # v3 优先：先遇到已存在 SKU 则跳过（后文件的同名 SKU 不覆盖）
                if sku in all_rows:
                    continue

                # 空 URL（含 pandas 的 nan）也预建 SKU，只记 rows_no_url
                url_str = str(ec_url) if ec_url is not None else ""
                if not ec_url or url_str.lower() == "nan":
                    result.rows_no_url += 1
                    all_rows[sku] = {"sku": sku, "asin": None, "source_url": None}
                    continue

                asin = extract_asin_from_url(ec_url)

                # 短链展开
                if asin is None and is_short_link(ec_url) and self.expand_short_links:
                    expanded = expand_short_link(ec_url)
                    if expanded:
                        asin = extract_asin_from_url(expanded)
                        if asin:
                            result.short_links_expanded += 1
                            ec_url = expanded   # 顺便把展开后的完整 URL 也存进去
                        else:
                            result.short_links_failed += 1
                    else:
                        result.short_links_failed += 1
                    time.sleep(self.EXPAND_SHORT_LINK_DELAY)

                all_rows[sku] = {
                    "sku": sku,
                    "asin": asin,
                    "source_url": ec_url,
                }

        # === 写入数据库 ===
        with get_session() as sess:
            existing = {p.sku: p for p in sess.execute(select(Product)).scalars().all()}

            for sku, data in all_rows.items():
                if sku in existing:
                    p = existing[sku]
                    changed = (p.asin != data["asin"]) or (p.source_url != data["source_url"])
                    if changed:
                        p.asin = data["asin"]
                        p.source_url = data["source_url"]
                        result.sku_updated += 1
                    else:
                        result.sku_unchanged += 1
                else:
                    sess.add(Product(
                        sku=sku,
                        title=None,           # 留空，等 D13 eBay 同步回填
                        asin=data["asin"],
                        source_url=data["source_url"],
                        cost_price=None,      # 等 Brief 2 注入
                        cost_currency="JPY",
                        supplier=None,
                        status=ProductStatus.ACTIVE,   # 默认，D13 后自动校正
                        variant_note=None,
                    ))
                    result.sku_inserted += 1

        return result

    def _read_excel(self, path: Path) -> pd.DataFrame:
        df = pd.read_excel(path, sheet_name=self.SHEET_NAME, header=self.HEADER_ROW)
        if self.DROP_FIRST_DATA_ROW:
            df = df.iloc[1:]
        return df

    @staticmethod
    def _clean_str(v) -> Optional[str]:
        if v is None:
            return None
        s = str(v).strip()
        if s in ("", "nan", "None"):
            return None
        return s
