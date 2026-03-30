"""
matcher/manual_review.py — 手动审核 CLI

交互式审核未匹配的采购记录和快递记录。
"""
import sqlite3
from datetime import datetime, timedelta
from db.db import get_connection, fetch_all, insert


class ManualReviewer:
    """手动审核器"""

    def __init__(self, review_type: str = "all", min_confidence: float = 0.0, max_confidence: float = 1.0):
        """
        Args:
            review_type: 'purchase' | 'shipment' | 'all'
            min_confidence: 最低置信度过滤（只看低于此值的记录）
            max_confidence: 最高置信度过滤（只看高于此值的记录）
        """
        self.review_type = review_type
        self.min_confidence = min_confidence
        self.max_confidence = max_confidence
        self.stats = {'confirmed': 0, 'skipped': 0, 'no_match': 0}

    def run(self) -> dict:
        """运行审核流程，返回统计结果"""
        if self.review_type == "purchase" or self.review_type == "all":
            self._review_purchases()

        if self.review_type == "shipment" or self.review_type == "all":
            self._review_shipments()

        return self.stats

    def _print_separator(self):
        print("═" * 52)

    def _review_purchases(self):
        """审核未匹配采购"""
        purchases = self._get_unmatched_purchases()

        if not purchases:
            print("\n[green]✓[/green] 没有待审核的采购记录")
            return

        print(f"\n[bold]开始审核采购记录，共 {len(purchases)} 条[/bold]\n")

        for idx, purchase in enumerate(purchases):
            self._print_separator()
            print(f"[采购记录 {idx + 1}/{len(purchases)}]")
            print(f"  采购 ID   : {purchase['id']}")
            print(f"  日期     : {purchase['purchase_date']}")
            print(f"  商品名   : {purchase['item_name']}")
            print(f"  ASIN     : {purchase.get('item_sku') or 'N/A'}")
            print(f"  单价     : ¥{purchase.get('unit_price_jpy') or 0:,.0f} × {purchase.get('quantity') or 1} = ¥{purchase.get('total_price_jpy') or 0:,.0f}")

            # 获取候选 eBay 订单
            candidates = self._get_candidates_for_purchase(purchase)

            if candidates:
                print("\n候选 eBay 订单：")
                for i, cand in enumerate(candidates, 1):
                    confidence = cand.get('confidence') or 0
                    title = (cand.get('item_title') or '')[:40]
                    print(f"  [{i}] {cand['order_id']}  {cand['sale_date']}  {title}...  ${cand.get('sale_price_usd') or 0:.2f}  (置信度：{confidence:.2f})")
            else:
                print("\n候选 eBay 订单：无")

            print("\n操作：[1/2/3] 确认匹配  [s] 跳过  [n] 标记无对应订单  [q] 退出")

            while True:
                try:
                    choice = input("> ").strip().lower()
                except (EOFError, KeyboardInterrupt):
                    print("\n\n审核中断。")
                    return

                if choice == 'q':
                    print("\n审核中断，下次继续。")
                    return
                elif choice == 's':
                    self.stats['skipped'] += 1
                    break
                elif choice == 'n':
                    self._mark_no_match('purchase', purchase['id'])
                    self.stats['no_match'] += 1
                    break
                elif choice.isdigit() and 1 <= int(choice) <= len(candidates):
                    selected = candidates[int(choice) - 1]
                    self._confirm_purchase_match(purchase['id'], selected['order_id'])
                    self.stats['confirmed'] += 1
                    break
                else:
                    print("无效输入，请重试。")

        print("\n")
        self._print_separator()
        print("采购审核完成！")

    def _review_shipments(self):
        """审核未匹配快递"""
        shipments = self._get_unmatched_shipments()

        if not shipments:
            print("\n[green]✓[/green] 没有待审核的快递记录")
            return

        print(f"\n[bold]开始审核快递记录，共 {len(shipments)} 条[/bold]\n")

        for idx, shipment in enumerate(shipments):
            self._print_separator()
            print(f"[快递记录 {idx + 1}/{len(shipments)}]")
            print(f"  快递 ID        : {shipment['id']}")
            print(f"  CPass 单号     : {shipment.get('tracking_number') or 'N/A'}")
            print(f"  发货日期      : {shipment.get('ship_date') or 'N/A'}")
            print(f"  运费          : ${shipment.get('shipping_fee_usd') or 0:.2f}")
            print(f"  目前状态      : {'未匹配' if not shipment.get('ebay_order_id') else '待确认'}")

            # 获取候选 eBay 订单
            candidates = self._get_candidates_for_shipment(shipment)

            if candidates:
                print("\n候选 eBay 订单（发货日期 ±5 天内）：")
                for i, cand in enumerate(candidates, 1):
                    tracking = cand.get('tracking_number') or '(空)'
                    # 检查是否精确单号匹配
                    match_hint = " (精确单号匹配)" if tracking == shipment.get('tracking_number') else ""
                    print(f"  [{i}] {cand['order_id']}  {cand['sale_date']}  跟踪号：{tracking}{match_hint}")
            else:
                print("\n候选 eBay 订单：无")

            print("\n操作：[1/2] 确认匹配  [s] 跳过  [n] 标记异常快递  [q] 退出")

            while True:
                try:
                    choice = input("> ").strip().lower()
                except (EOFError, KeyboardInterrupt):
                    print("\n\n审核中断。")
                    return

                if choice == 'q':
                    print("\n审核中断，下次继续。")
                    return
                elif choice == 's':
                    self.stats['skipped'] += 1
                    break
                elif choice == 'n':
                    self._mark_no_match('shipment', shipment['id'])
                    self.stats['no_match'] += 1
                    break
                elif choice.isdigit() and 1 <= int(choice) <= len(candidates):
                    selected = candidates[int(choice) - 1]
                    self._confirm_shipment_match(shipment['id'], selected['order_id'])
                    self.stats['confirmed'] += 1
                    break
                else:
                    print("无效输入，请重试。")

        print("\n")
        self._print_separator()
        print("快递审核完成！")

    def _get_unmatched_purchases(self) -> list:
        """获取未匹配或低置信度的采购记录"""
        # 已确认或标记无匹配的记录不显示
        query = """
            SELECT p.* FROM purchases p
            LEFT JOIN purchase_order_links pol ON p.id = pol.purchase_id
            WHERE pol.confirmed_by IS NULL
              AND (p.no_match_reason IS NULL OR p.no_match_reason = '')
            ORDER BY p.purchase_date
        """
        return fetch_all(query)

    def _get_candidates_for_purchase(self, purchase: dict) -> list:
        """获取采购的候选 eBay 订单（按日期和商品名相似度）"""
        purchase_date = purchase.get('purchase_date')
        if not purchase_date:
            return []

        # 获取前后 15 天的 eBay 订单
        try:
            dt = datetime.strptime(purchase_date, '%Y-%m-%d')
            start = (dt - timedelta(days=15)).strftime('%Y-%m-%d')
            end = (dt + timedelta(days=15)).strftime('%Y-%m-%d')
        except ValueError:
            return []

        candidates = fetch_all("""
            SELECT order_id, sale_date, item_title, sale_price_usd,
                   (SELECT confidence FROM purchase_order_links 
                    WHERE ebay_order_id = eo.order_id AND purchase_id = ?
                    ORDER BY confidence DESC LIMIT 1) as confidence
            FROM ebay_orders eo
            WHERE strftime('%Y-%m-%d', sale_date) BETWEEN ? AND ?
            ORDER BY sale_date
            LIMIT 5
        """, (purchase['id'], start, end))

        return candidates

    def _get_unmatched_shipments(self) -> list:
        """获取未匹配的快递记录"""
        return fetch_all("""
            SELECT * FROM shipments
            WHERE ebay_order_id IS NULL
            ORDER BY ship_date
        """)

    def _get_candidates_for_shipment(self, shipment: dict) -> list:
        """获取快递的候选 eBay 订单（按发货日期 ±5 天）"""
        ship_date = shipment.get('ship_date')
        if not ship_date:
            return []

        try:
            dt = datetime.strptime(ship_date, '%Y-%m-%d')
            start = (dt - timedelta(days=5)).strftime('%Y-%m-%d')
            end = (dt + timedelta(days=5)).strftime('%Y-%m-%d')
        except ValueError:
            return []

        tracking = shipment.get('tracking_number')

        # 优先返回跟踪号匹配的订单
        if tracking:
            exact_match = fetch_all("""
                SELECT order_id, sale_date, item_title, tracking_number
                FROM ebay_orders
                WHERE tracking_number = ?
            """, (tracking,))
            if exact_match:
                return exact_match

        return fetch_all("""
            SELECT order_id, sale_date, item_title, tracking_number
            FROM ebay_orders
            WHERE strftime('%Y-%m-%d', sale_date) BETWEEN ? AND ?
            ORDER BY sale_date
            LIMIT 5
        """, (start, end))

    def _confirm_purchase_match(self, purchase_id: str, order_id: str):
        """确认采购匹配"""
        with get_connection() as conn:
            # 插入或更新匹配关系
            conn.execute("""
                INSERT OR REPLACE INTO purchase_order_links
                (purchase_id, ebay_order_id, match_method, confidence, confirmed_by)
                VALUES (?, ?, 'manual', 1.0, 'user')
            """, (purchase_id, order_id))
        print(f"  [green]✓[/green] 已确认匹配：{purchase_id} → {order_id}")

    def _confirm_shipment_match(self, shipment_id: str, order_id: str):
        """确认快递匹配"""
        with get_connection() as conn:
            conn.execute("""
                UPDATE shipments
                SET ebay_order_id = ?, match_method = 'manual', confirmed_by = 'user'
                WHERE id = ?
            """, (order_id, shipment_id))
        print(f"  [green]✓[/green] 已确认匹配：{shipment_id} → {order_id}")

    def _mark_no_match(self, record_type: str, record_id: str):
        """标记无对应订单"""
        with get_connection() as conn:
            if record_type == 'purchase':
                conn.execute("""
                    UPDATE purchases
                    SET no_match_reason = 'no_ebay_order'
                    WHERE id = ?
                """, (record_id,))
            elif record_type == 'shipment':
                # 外键约束：ebay_order_id 必须为 NULL 或有效的 order_id
                # 使用 match_method='manual' + confirmed_by='user' 标记为已审核但无匹配
                conn.execute("""
                    UPDATE shipments
                    SET match_method = 'manual', confirmed_by = 'user'
                    WHERE id = ?
                """, (record_id,))
        print(f"  [yellow]✓[/yellow] 已标记无匹配：{record_id}")
