"""
modules/inventory_online/price_monitor.py

Day 16: 供应价格变化检测 + 阈值警告

功能：
- update_cost_price(sku, new_price)：更新进货价并记录历史
- 如果 |new_price - old_price| / old_price > threshold，发布 PRICE_ALERT 事件
- 利润影响分析：新利润率 < 最低阈值时建议调整售价
- 批量价格更新（从 CSV）
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path

from loguru import logger as log


# 默认阈值
DEFAULT_PRICE_CHANGE_THRESHOLD = 0.10  # 10%
DEFAULT_MIN_PROFIT_MARGIN = 0.15       # 15%


@dataclass
class PriceChangeAlert:
    """价格变化预警信息。"""
    sku: str
    title: str | None
    old_price: Decimal
    new_price: Decimal
    change_rate: float       # 正数=涨，负数=跌
    direction: str          # up / down / unchanged
    threshold: float
    triggered: bool          # 是否超过阈值
    old_listing_price: float | None
    new_margin: float | None   # 新利润率（基于当前售价）
    suggested_action: str      # 建议操作


@dataclass
class BatchPriceUpdateResult:
    """批量价格更新结果。"""
    total: int
    success: int
    failed: int
    alerts: list[PriceChangeAlert]
    errors: list[dict]   # [{sku, error}]


class PriceMonitor:
    """价格监控服务。"""

    def __init__(
        self,
        price_change_threshold: float = DEFAULT_PRICE_CHANGE_THRESHOLD,
        min_profit_margin: float = DEFAULT_MIN_PROFIT_MARGIN,
    ):
        from core.config.settings import settings
        self._settings = settings
        self.threshold = price_change_threshold
        self.min_margin = min_profit_margin

    # ── 核心：更新进货价 ──────────────────────────────────────────────────

    def update_cost_price(
        self,
        sku: str,
        new_price: Decimal | float | str,
        supplier: str | None = None,
        note: str | None = None,
    ) -> PriceChangeAlert:
        """
        更新 SKU 的进货价，同时：
        1. 将旧价格记录到 SupplierPriceHistory 表
        2. 如果变化超过阈值，发布 PRICE_ALERT 事件
        3. 计算新利润率，返回预警信息

        Returns:
            PriceChangeAlert: 变化详情

        Raises:
            ValueError: SKU 不存在或价格格式无效
        """
        from core.database.connection import get_session
        from core.models import Product
        from core.models.price_history import SupplierPriceHistory
        from core.events.bus import EventBus

        try:
            new_price = Decimal(str(new_price))
        except (InvalidOperation, TypeError) as e:
            raise ValueError(f"无效的进货价: {new_price!r}") from e

        if new_price <= 0:
            raise ValueError(f"进货价必须 > 0: {new_price}")

        with get_session() as sess:
            product = sess.query(Product).filter(Product.sku == sku).first()
            if not product:
                raise ValueError(f"SKU 不存在: {sku}")

            old_price = product.cost_price
            old_listing_price = None

            # 获取当前 eBay 售价（用于计算利润率）
            from core.models import EbayListing
            listing = sess.query(EbayListing).filter(EbayListing.sku == sku).first()
            if listing and listing.listing_price:
                old_listing_price = float(listing.listing_price)

            # 1) 记录旧价格到历史表
            history = SupplierPriceHistory(
                sku=sku,
                supplier=supplier or product.supplier,
                price=old_price,
                currency=product.cost_currency,
            )
            sess.add(history)

            # 2) 更新 Product 表
            product.cost_price = new_price
            if supplier:
                product.supplier = supplier

            # 3) 计算变化率
            if old_price > 0:
                change_rate = (new_price - old_price) / old_price
                change_rate_float = float(change_rate)
            else:
                change_rate_float = 0.0

            if abs(change_rate_float) < 1e-9:
                direction = "unchanged"
            elif change_rate_float > 0:
                direction = "up"
            else:
                direction = "down"

            triggered = abs(change_rate_float) > self.threshold

            # 4) 利润率计算
            new_margin: float | None = None
            suggested_action = "无需操作"
            if old_listing_price and old_listing_price > 0:
                cost_jpy = float(new_price)
                # 简单利润率 = (售价 - 成本) / 售价
                new_margin = (old_listing_price - cost_jpy) / old_listing_price
                if new_margin < self.min_margin:
                    suggested_action = (
                        f"利润率 {new_margin:.1%} 低于最低阈值 {self.min_margin:.1%}，"
                        f"建议调整售价至 ¥{cost_jpy / (1 - self.min_margin):.0f} 以上"
                    )

            # 5) 发布事件
            alert = PriceChangeAlert(
                sku=sku,
                title=product.title,
                old_price=old_price,
                new_price=new_price,
                change_rate=change_rate_float,
                direction=direction,
                threshold=self.threshold,
                triggered=triggered,
                old_listing_price=old_listing_price,
                new_margin=new_margin,
                suggested_action=suggested_action,
            )

            if triggered:
                bus = EventBus()
                bus.publish(
                    event_type="PRICE_ALERT",
                    payload={
                        "sku": sku,
                        "title": product.title,
                        "old_price": float(old_price),
                        "new_price": float(new_price),
                        "change_rate": change_rate_float,
                        "direction": direction,
                        "threshold": self.threshold,
                        "old_listing_price": old_listing_price,
                        "new_margin": new_margin,
                        "suggested_action": suggested_action,
                        "message": (
                            f"{sku} 进货价变化 {direction}: "
                            f"¥{old_price} → ¥{new_price} "
                            f"({change_rate_float:+.1%})"
                        ),
                    },
                )
                log.warning(
                    f"PRICE_ALERT: {sku} 进货价变化 {change_rate_float:+.1%}，"
                    f"建议: {suggested_action}"
                )

            return alert

    # ── 批量价格更新 ─────────────────────────────────────────────────────

    def batch_update_from_csv(
        self,
        csv_path: str | Path,
        supplier: str | None = None,
    ) -> BatchPriceUpdateResult:
        """
        从 CSV 批量更新进货价。

        CSV 格式（header 行必须）：
            sku, new_price, supplier（可选）, note（可选）

        Returns:
            BatchPriceUpdateResult
        """
        csv_path = Path(csv_path)
        if not csv_path.exists():
            raise FileNotFoundError(f"CSV 文件不存在: {csv_path}")

        alerts: list[PriceChangeAlert] = []
        errors: list[dict] = []
        success = 0

        with open(csv_path, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            rows = list(reader)

        for row in rows:
            sku = (row.get("sku") or "").strip()
            price_val = (row.get("new_price") or "").strip()
            row_supplier = (row.get("supplier") or "").strip() or supplier
            row_note = (row.get("note") or "").strip()

            if not sku:
                errors.append({"row": row, "error": "sku 为空"})
                continue

            try:
                alert = self.update_cost_price(
                    sku=sku,
                    new_price=price_val,
                    supplier=row_supplier,
                    note=row_note or None,
                )
                alerts.append(alert)
                success += 1
            except Exception as e:
                log.error(f"更新 {sku} 失败: {e}")
                errors.append({"sku": sku, "error": str(e)})

        return BatchPriceUpdateResult(
            total=len(rows),
            success=success,
            failed=len(rows) - success,
            alerts=alerts,
            errors=errors,
        )

    # ── 价格历史查询 ─────────────────────────────────────────────────────

    def get_price_history(self, sku: str) -> list:
        """获取 SKU 的价格变动历史（从新到旧）。"""
        from core.database.connection import get_session
        from core.models.price_history import SupplierPriceHistory

        with get_session() as sess:
            records = (
                sess.query(SupplierPriceHistory)
                .filter(SupplierPriceHistory.sku == sku)
                .order_by(SupplierPriceHistory.recorded_at.desc())
                .all()
            )
            return records

    def get_latest_price(self, sku: str) -> Decimal | None:
        """获取 SKU 最新进货价（从 Product 表）。"""
        from core.database.connection import get_session
        from core.models import Product

        with get_session() as sess:
            p = sess.query(Product).filter(Product.sku == sku).first()
            return p.cost_price if p else None
