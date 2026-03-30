"""
matcher/purchase_order.py — 采购与订单匹配引擎（v2 三层匹配 + FIFO）

匹配策略（按优先级）：
1. Layer 1 - 锚点精确匹配：ASIN / SKU 精确匹配 → 置信度 1.0
2. Layer 2 - 品牌词典模糊匹配：使用日英品牌对照 + 商品名模糊匹配 → 置信度 0.7~0.95
3. Layer 3 - 日期窗口过滤匹配：采购日期±7 天内，相似商品 + 价格接近 → 置信度 0.5~0.7
"""
from datetime import datetime, timedelta
from rapidfuzz import fuzz
from db.db import fetch_all, execute, insert
from matcher.brand_dict import extract_brand_from_text, brand_match


def match_purchase_order() -> dict:
    """
    将 purchases 表与 ebay_orders 表进行三层匹配

    返回：
        {
            "matched": int,
            "unmatched": int,
            "layer1": int,  # 锚点精确匹配数量
            "layer2": int,  # 品牌词典匹配数量
            "layer3": int   # 日期窗口匹配数量
        }
    """
    # 清空旧的匹配记录（保留手动确认的）
    execute("DELETE FROM purchase_order_links WHERE match_method != 'manual'")
    
    stats = {"matched": 0, "unmatched": 0, "layer1": 0, "layer2": 0, "layer3": 0}
    
    # 获取所有采购记录
    purchases = fetch_all("SELECT * FROM purchases ORDER BY purchase_date")
    # 获取所有 eBay 订单
    ebay_orders = fetch_all("SELECT * FROM ebay_orders ORDER BY sale_date")
    
    # 追踪已匹配的订单
    matched_order_ids = set()
    
    # Layer 1: 锚点精确匹配 (ASIN / SKU)
    for purchase in purchases:
        purchase_sku = (purchase.get('item_sku') or '').strip()
        if not purchase_sku:
            continue
        
        for order in ebay_orders:
            if order['order_id'] in matched_order_ids:
                continue
            
            order_item_id = (order.get('item_id') or '').strip()
            if purchase_sku.upper() == order_item_id.upper():
                _save_match(purchase, order, 'anchor', 1.0)
                matched_order_ids.add(order['order_id'])
                stats["matched"] += 1
                stats["layer1"] += 1
                break
    
    # Layer 2: 品牌词典模糊匹配
    for purchase in purchases:
        purchase_name = purchase.get('item_name') or ''
        if not purchase_name:
            continue
        
        for order in ebay_orders:
            if order['order_id'] in matched_order_ids:
                continue
            
            order_title = order.get('item_title') or ''
            if not order_title:
                continue
            
            # 检查品牌是否匹配
            if not brand_match(purchase_name, order_title):
                continue
            
            # 品牌匹配后，检查商品名相似度
            ratio = fuzz.token_sort_ratio(purchase_name, order_title)
            if ratio >= 75:
                confidence = 0.7 + (ratio - 75) / 100 * 0.25  # 0.7 ~ 0.95
                _save_match(purchase, order, 'brand_dict', confidence)
                matched_order_ids.add(order['order_id'])
                stats["matched"] += 1
                stats["layer2"] += 1
                break
    
    # Layer 3: 日期窗口过滤匹配
    for purchase in purchases:
        purchase_date_str = purchase.get('purchase_date')
        if not purchase_date_str:
            continue
        
        try:
            purchase_date = datetime.strptime(purchase_date_str, '%Y-%m-%d')
        except ValueError:
            continue
        
        purchase_name = purchase.get('item_name') or ''
        purchase_price = purchase.get('total_price_jpy') or 0
        
        for order in ebay_orders:
            if order['order_id'] in matched_order_ids:
                continue
            
            order_date_str = order.get('sale_date')
            if not order_date_str:
                continue
            
            try:
                order_date = datetime.strptime(order_date_str, '%Y-%m-%d')
            except ValueError:
                continue
            
            # 检查日期窗口（±7 天）
            date_diff = abs((order_date - purchase_date).days)
            if date_diff > 7:
                continue
            
            order_title = order.get('item_title') or ''
            if not order_title:
                continue
            
            # 商品名相似度
            ratio = fuzz.token_sort_ratio(purchase_name, order_title)
            if ratio < 70:
                continue
            
            # 价格检查（粗略：假设 1 USD ≈ 150 JPY）
            order_price_usd = (order.get('sale_price_usd') or 0) + (order.get('shipping_charged_usd') or 0)
            order_price_jpy = order_price_usd * 150
            price_ratio = min(purchase_price, order_price_jpy) / max(purchase_price, order_price_jpy) if max(purchase_price, order_price_jpy) > 0 else 0
            
            if price_ratio < 0.7:  # 价格差异超过 30% 则不匹配
                continue
            
            # 计算置信度
            confidence = 0.5 + (ratio / 100) * 0.15 + price_ratio * 0.05  # 0.5 ~ 0.7
            _save_match(purchase, order, 'date_window', confidence)
            matched_order_ids.add(order['order_id'])
            stats["matched"] += 1
            stats["layer3"] += 1
            break
    
    # 统计未匹配
    stats["unmatched"] = len(ebay_orders) - stats["matched"]
    
    return stats


def _save_match(purchase: dict, order: dict, method: str, confidence: float):
    """保存匹配记录"""
    existing = fetch_all("""
        SELECT * FROM purchase_order_links
        WHERE purchase_id = ? AND ebay_order_id = ?
    """, (purchase['id'], order['order_id']))
    
    if not existing:
        insert('purchase_order_links', {
            'purchase_id': purchase['id'],
            'ebay_order_id': order['order_id'],
            'match_method': method,
            'confidence': round(confidence, 3)
        })


def allocate_fifo() -> dict:
    """
    为所有匹配成功的订单执行 FIFO 成本分配
    
    返回：
        {"allocated": int, "skipped": int}
    """
    # 获取所有已匹配但尚未分配成本的记录
    links = fetch_all("""
        SELECT pol.*, p.quantity as purchase_qty, p.total_price_jpy, p.tax_jpy, p.purchase_date
        FROM purchase_order_links pol
        JOIN purchases p ON pol.purchase_id = p.id
        WHERE pol.allocated_qty IS NULL
        ORDER BY p.purchase_date ASC
    """)
    
    allocated_count = 0
    skipped_count = 0
    
    # 按订单分组
    orders = {}
    for link in links:
        order_id = link['ebay_order_id']
        if order_id not in orders:
            orders[order_id] = []
        orders[order_id].append(link)
    
    for order_id, order_links in orders.items():
        # 获取订单数量
        order = fetch_all("SELECT quantity FROM ebay_orders WHERE order_id = ?", (order_id,))
        if not order:
            continue
        order_qty = order[0]['quantity']
        
        # 按采购日期排序
        order_links.sort(key=lambda x: x['purchase_date'] or '')
        
        remaining_qty = order_qty
        for link in order_links:
            if remaining_qty <= 0:
                break
            
            available_qty = link['purchase_qty'] - (link['allocated_qty'] or 0)
            if available_qty <= 0:
                continue
            
            allocate_qty = min(remaining_qty, available_qty)
            unit_cost = (link['total_price_jpy'] or 0) / link['purchase_qty'] if link['purchase_qty'] and link['purchase_qty'] > 0 else 0
            unit_tax = (link['tax_jpy'] or 0) / link['purchase_qty'] if link['purchase_qty'] and link['purchase_qty'] > 0 else 0
            
            execute("""
                UPDATE purchase_order_links
                SET allocated_qty = ?, allocated_cost_jpy = ?, allocated_tax_jpy = ?
                WHERE id = ?
            """, (allocate_qty, unit_cost * allocate_qty, unit_tax * allocate_qty, link['id']))
            
            remaining_qty -= allocate_qty
            allocated_count += 1
        
        if remaining_qty > 0:
            skipped_count += 1
    
    return {"allocated": allocated_count, "skipped": skipped_count}


def update_inventory():
    """重建库存表"""
    execute("DELETE FROM inventory")
    
    inventory_data = fetch_all("""
        SELECT 
            p.item_sku,
            p.item_name,
            p.item_name_en,
            SUM(p.quantity) as total_quantity,
            SUM(COALESCE(pol.allocated_qty, 0)) as sold_quantity,
            SUM(p.total_price_jpy) as total_cost_jpy,
            SUM(p.tax_jpy) as total_tax_jpy
        FROM purchases p
        LEFT JOIN purchase_order_links pol ON p.id = pol.purchase_id
        WHERE p.item_sku IS NOT NULL
        GROUP BY p.item_sku
    """)
    
    for item in inventory_data:
        remaining = item['total_quantity'] - item['sold_quantity']
        avg_cost = item['total_cost_jpy'] / item['total_quantity'] if item['total_quantity'] > 0 else 0
        
        insert('inventory', {
            'id': f"inv_{item['item_sku']}_{datetime.now().strftime('%Y%m%d%H%M%S')}",
            'item_sku': item['item_sku'],
            'item_name': item['item_name'],
            'item_name_en': item['item_name_en'],
            'total_quantity': item['total_quantity'],
            'sold_quantity': item['sold_quantity'],
            'remaining_quantity': remaining,
            'total_cost_jpy': item['total_cost_jpy'],
            'total_tax_jpy': item['total_tax_jpy'],
            'average_cost_per_unit': avg_cost
        })
