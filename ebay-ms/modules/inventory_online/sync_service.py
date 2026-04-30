"""
Day 13: 拉取 eBay Active Listings 同步到本地

全量同步：GET /sell/inventory/v1/inventory_item 分页拉取所有库存项，
按 ebay_item_id upsert 到 EbayListing 表。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from loguru import logger as log

if TYPE_CHECKING:
    from core.ebay_api.client import EbayClient


PAGE_SIZE = 100  # eBay 每页最大返回数


@dataclass
class SyncResult:
    """同步结果报告。"""
    total_on_ebay: int = 0
    new_count: int = 0
    updated_count: int = 0
    ended_count: int = 0
    error_count: int = 0
    errors: list[str] = field(default_factory=list)

    def summary(self) -> str:
        return (
            f"同步完成: eBay 在售 {self.total_on_ebay} 条 | "
            f"新增 {self.new_count} | 更新 {self.updated_count} | "
            f"下架 {self.ended_count} | 错误 {self.error_count}"
        )


class SyncService:
    """eBay 在线库存同步服务。"""

    def __init__(self, client: EbayClient | None = None):
        from core.ebay_api.client import EbayClient

        self.client = client or EbayClient()

    def full_sync(self, incremental: bool = False, dry_run: bool = False) -> SyncResult:
        """全量同步所有活跃 listing 到本地 EbayListing 表。

        Args:
            incremental: 如果为 True，只同步自上次 sync 以来的变化。

        Returns:
            SyncResult: 同步统计报告。
        """
        result = SyncResult()
        log.info("开始全量同步 eBay inventory...")

        # 获取所有 inventory items（分页）
        try:
            all_items = self._fetch_all_inventory_items()
        except Exception as exc:
            log.error(f"拉取 eBay inventory 失败: {exc}")
            result.errors.append(f"API 拉取失败: {exc}")
            result.error_count += 1
            return result
        result.total_on_ebay = len(all_items)
        log.info(f"eBay 返回 {result.total_on_ebay} 条 inventory items")

        # 收集 eBay 上当前所有 sku
        current_skus = {item["sku"] for item in all_items if item.get("sku")}

        # Upsert 每条记录
        listings_with_variants = 0
        variant_samples = []
        for item in all_items:
            try:
                # 检查 variants 是否非空（用于 dry-run 统计）
                raw_variants = item.get("variants") or item.get("variantSummaries")
                has_variants = raw_variants not in (None, {}, "null", "[]")
                if has_variants:
                    listings_with_variants += 1
                    if len(variant_samples) < 3:
                        variant_samples.append({
                            "sku": item.get("sku", "?"),
                            "variants": raw_variants,
                        })

                if dry_run:
                    continue

                is_new = self._upsert_listing(item)
                if is_new:
                    result.new_count += 1
                else:
                    result.updated_count += 1
            except Exception as exc:
                result.error_count += 1
                result.errors.append(f"[{item.get('sku','?')}] {exc}")
                log.error(f"Upsert listing 失败 sku={item.get('sku')}: {exc}")

        # dry-run: 打印预览
        if dry_run:
            print("=== inventory online sync --dry-run ===")
            print(f"EbayListing 总数: {result.total_on_ebay}")
            print(f"带 variants: {listings_with_variants} 条")
            if variant_samples:
                print(f"\n样本（前 {len(variant_samples)} 条）:")
                import json
                for s in variant_samples:
                    print(f"  SKU={s['sku']}: {json.dumps(s['variants'])[:200]}")
            return result

        # 标记已下架的记录（本地有但 eBay 不再有）
        ended_skus = self._mark_ended_listings(current_skus)
        result.ended_count = ended_skus

        log.info(f"同步完成: {result.summary()}")
        return result

    def _fetch_all_inventory_items(self) -> list[dict]:
        """分页拉取所有 inventory items。

        eBay API: GET /sell/inventory/v1/inventory_item
        响应: { total: int, skuInventoryItems: [...] }
        """
        items: list[dict] = []
        offset = 0

        while True:
            resp = self.client.get(
                "/sell/inventory/v1/inventory_item",
                params={"offset": offset, "limit": PAGE_SIZE},
            )
            batch = resp.get("inventoryItems", [])
            if not batch:
                break
            items.extend(batch)
            total = resp.get("total", 0)
            log.debug(f"  Page offset={offset}: {len(batch)} 条 (累计 {len(items)}/{total})")
            if len(items) >= total:
                break
            offset += PAGE_SIZE

        return items

    def _upsert_listing(self, item: dict, dry_run: bool = False) -> bool:
        """将一条 eBay inventory item upsert 到 EbayListing 表。

        Args:
            item: eBay inventory item dict.
            dry_run: 如果 True，不写库，只返回结果。

        Returns:
            True if new record created, False if updated.
        """
        from core.database.connection import get_session
        from core.models import EbayListing, ListingStatus

        sku = item.get("sku", "")
        # eBay inventory item 没有直接的 ebay_item_id，
        # 我们用 sku 关联，本地自己生成 uuid
        # 实际上 eBay inventory API 中每个 SKU 对应一个 inventory item，
        # 发布后的 offer 才有 ebay_item_id
        # 这里把 sku 作为本地 EbayListing.sku 关联键
        inventory = item.get("availability", {}).get("shipToLocationAvailability", {})
        quantity = inventory.get("availableQuantity", 0)

        # 查找对应 listing 的 price
        pricing = item.get("pricingSummaries", [])
        price = None
        for p in pricing:
            if p.get("price", {}).get("value"):
                price = float(p.get("price", {}).get("value"))
                break

        now = datetime.now(timezone.utc)

        # 提取 variants（多属性变体信息）
        raw_variants = item.get("variants") or item.get("variantSummaries")

        with get_session() as sess:
            existing = sess.query(EbayListing).filter(
                EbayListing.sku == sku
            ).first()

            if existing:
                # Update
                if quantity is not None:
                    existing.quantity_available = quantity
                if price is not None:
                    existing.listing_price = price
                existing.status = ListingStatus.ACTIVE
                existing.last_synced = now
                if raw_variants:
                    existing.variants = raw_variants
                sess.commit()
                return False
            else:
                # Create
                listing = EbayListing(
                    ebay_item_id=sku,  # 暂时用 sku 作为 item_id 等价物
                    sku=sku,
                    listing_price=price or 0.0,
                    quantity_available=quantity or 0,
                    status=ListingStatus.ACTIVE,
                    last_synced=now,
                    variants=raw_variants,
                )
                sess.add(listing)
                sess.commit()
                return True

    def _mark_ended_listings(self, current_skus: set[str]) -> int:
        """将本地有但 eBay 不再有的 listing 标记为 ENDED。

        Returns:
            Number of listings marked as ended.
        """
        from core.database.connection import get_session
        from core.models import EbayListing, ListingStatus

        with get_session() as sess:
            all_local = sess.query(EbayListing).filter(
                EbayListing.status == ListingStatus.ACTIVE
            ).all()

            ended = 0
            for listing in all_local:
                if listing.sku not in current_skus:
                    listing.status = ListingStatus.ENDED
                    ended += 1

            sess.commit()
            if ended:
                log.info(f"标记 {ended} 条 listing 为 ENDED")
            return ended
