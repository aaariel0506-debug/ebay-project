"""
modules/inventory_online/event_handlers.py

Day 22: 线上线下库存联动

监听 STOCK_OUT 事件，自动扣减 eBay 在线库存。
防止同一订单重复扣减（用 related_order 去重）。
"""

from loguru import logger as log


def handle_stock_out(event_type: str, payload: dict) -> None:
    """
    STOCK_OUT 事件处理器。

    流程：
    1. 解析 payload（sku / quantity / related_order）
    2. 防重复扣减：查询 event_log 中是否有同 related_order 的 DONE STOCK_OUT
    3. 查询本地 EbayListing
    4. 计算新库存数量，调用 QuantityAdjuster 扣减 eBay 库存

    Args:
        event_type: 事件类型（STOCK_OUT）
        payload: {
            "sku": str,
            "quantity": int,          # 出库数量
            "related_order": str,     # 关联订单号（用于去重）
            "cost_price": str,        # 进货价（可选）
            "operator": str,
            "occurred_at": str,
        }
    """
    from core.database.connection import get_session
    from core.events.models import EventLog, EventStatus
    from core.models import EbayListing
    from modules.inventory_online.quantity_adjuster import QuantityAdjuster

    sku = payload.get("sku")
    quantity = payload.get("quantity", 0)
    related_order = payload.get("related_order")

    if not sku:
        log.warning("STOCK_OUT handler: 收到空 sku，跳过")
        return

    if not quantity or quantity <= 0:
        log.info(f"STOCK_OUT handler: {sku} quantity={quantity}，跳过")
        return

    # ── 防重复扣减 ──────────────────────────────────────
    # related_order 记录在 STOCK_OUT 事件 payload 中。
    # 通过查询 event_log 中是否有同订单的 DONE STOCK_OUT 来去重。
    #
    # 注意：SQLite 不支持 JSON 列的 .astext 查询，
    # 因此这里取回所有 DONE STOCK_OUT 事件后在 Python 层做 payload 匹配。
    # 数据量大时效率低（O(N) 扫描）。
    # 未来优化方案：
    #   1. 在 EventLog 表加 related_order 独立字段并建索引
    #   2. 或改用 PostgreSQL 以支持 JSONB 查询
    if related_order:
        with get_session() as sess:
            dup = sess.query(EventLog).filter(
                EventLog.event_type == "STOCK_OUT",
                EventLog.status == EventStatus.DONE,
            ).all()
            for ev in dup:
                if ev.payload and ev.payload.get("related_order") == related_order:
                    log.info(
                        f"STOCK_OUT handler: {sku} + 订单 {related_order} 已处理过，跳过"
                    )
                    return

    # ── 查询 eBay Listing ─────────────────────────────────
    with get_session() as sess:
        listing = sess.query(EbayListing).filter(
            EbayListing.sku == sku
        ).first()

        if not listing:
            log.warning(f"STOCK_OUT handler: SKU {sku} 无 eBay listing，跳过")
            return

        if not listing.ebay_item_id:
            log.warning(f"STOCK_OUT handler: SKU {sku} 无 ebay_item_id，跳过")
            return

        current_qty = listing.quantity_available or 0

    # ── 计算新库存 ────────────────────────────────────────
    new_qty = max(current_qty - quantity, 0)
    if new_qty >= current_qty:
        log.info(
            f"STOCK_OUT handler: {sku} 当前库存 {current_qty}，出库 {quantity}，无需更新"
        )
        return

    # ── 调用 eBay API 扣减 ───────────────────────────────
    try:
        adjuster = QuantityAdjuster()
        result = adjuster.adjust_ebay_quantity(
            sku=sku,
            new_quantity=new_qty,
            publish_event=True,
        )
        if result.success:
            log.info(
                f"✅ STOCK_OUT → eBay 同步：{sku} {current_qty} → {new_qty}"
            )
        else:
            # adjust_ebay_quantity 内部捕获了 API 异常，
            # 返回 success=False；这里把它转为异常由 _dispatch 标记 FAILED
            raise RuntimeError(f"eBay 库存同步失败：{result.error}")
    except RuntimeError:
        # 已记录，向上抛由 _dispatch 捕获
        raise
    except Exception as e:
        log.error(f"❌ STOCK_OUT → eBay 同步异常：{sku} {e}")
        raise  # 由 _dispatch 捕获，标记 FAILED
