#!/usr/bin/env python3
"""
智能匹配采购和订单 - 使用日期 + 商品名 + 品牌
"""
import sqlite3
from rapidfuzz import fuzz, process

DB_PATH = '/Users/arielhe/.openclaw/workspace/ebay-tax-system/data/orders.db'

# 品牌关键词（日文 → 英文）
BRANDS = {
    '無印': ['MUJI', '无印'],
    '貝印': ['KAI', 'Kai Corporation'],
    'シルキー': ['Silky', 'ユーエム工業'],
    'タカラトミー': ['Takara Tomy', 'Tomy'],
    'バンダイ': ['Bandai', 'BANDAI'],
    'ソニー': ['Sony', 'SONY'],
    'パナソニック': ['Panasonic'],
    '三菱': ['Mitsubishi', 'Uni'],
    'ゼブラ': ['Zebra'],
    'ぺんてる': ['Pentel'],
    'サクラ': ['Sakura'],
    'トンボ': ['Tombow'],
    'コクヨ': ['Kokuyo'],
    'レイメイ': ['Raymay'],
    'リヒト': ['Lihit Lab'],
    'マルマン': ['Maruman'],
    'キングジム': ['King Jim'],
    'パイロット': ['Pilot'],
    'セーラー': ['Sailor'],
    'プラチナ': ['Platinum'],
    '緑屋': ['Midori'],
    'ほぼ日': ['Hobonichi'],
    '高橋': ['Takahashi'],
    '能率': ['Nok'],
    'アイリス': ['Iris'],
    '山崎': ['Yamazaki'],
    'エレコム': ['Elecom'],
    'バッファロー': ['Buffalo'],
    'サンワ': ['Sanwa'],
}

def get_brands(text):
    """从文本中提取品牌"""
    if not text:
        return []
    found = []
    for jp, ens in BRANDS.items():
        if jp in text:
            found.append(jp)
            found.extend(ens)
        for en in ens:
            if en in text.upper():
                found.append(en)
    return found

def match_products():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    
    # 获取 2 月份订单
    c.execute("SELECT * FROM ebay_orders WHERE strftime('%Y-%m', sale_date) = '2026-02'")
    orders = c.fetchall()
    
    # 获取 2 月份采购
    c.execute("SELECT * FROM purchases WHERE strftime('%Y-%m', purchase_date) = '2026-02'")
    purchases = c.fetchall()
    
    print(f"📦 订单数：{len(orders)}")
    print(f"📦 采购数：{len(purchases)}")
    
    # 清空旧匹配
    c.execute("DELETE FROM purchase_order_links")
    
    matched = 0
    unmatched_orders = []
    
    for order in orders:
        order_id = order['order_id']
        order_date = order['sale_date']
        order_title = (order['item_title'] or '').upper()
        order_qty = order['quantity']
        
        # 提取订单品牌
        order_brands = get_brands(order_title)
        
        best_match = None
        best_score = 0
        
        for purchase in purchases:
            purchase_date = purchase['purchase_date']
            purchase_name = (purchase['item_name'] or '').upper()
            purchase_asin = purchase['item_sku'] or ''
            purchase_qty = purchase['quantity']
            
            # 条件 1: 日期窗口（订单在采购后 7-30 天，即先采购后销售）
            if purchase_date and order_date:
                from datetime import datetime
                try:
                    p_date = datetime.strptime(purchase_date, '%Y-%m-%d')
                    o_date = datetime.strptime(order_date, '%Y-%m-%d')
                    days_diff = (o_date - p_date).days
                    # 订单日期应该在采购日期后 7-60 天（给一些缓冲）
                    if days_diff < 7 or days_diff > 60:
                        continue
                except:
                    continue
            
            # 条件 2: ASIN 匹配（如果有）
            asin_match = False
            if purchase_asin and purchase_asin in order_title:
                asin_match = True
            
            # 条件 3: 品牌匹配
            purchase_brands = get_brands(purchase_name)
            brand_match = True
            if order_brands and purchase_brands:
                # 有重叠品牌
                brand_match = bool(set(order_brands) & set(purchase_brands))
            elif order_brands and not purchase_brands:
                # 订单有品牌但采购没有，降低分数
                brand_match = True
            elif not order_brands and purchase_brands:
                # 采购有品牌但订单没有，降低分数
                brand_match = True
            
            if not brand_match:
                continue
            
            # 条件 4: 商品名相似度
            # 简化商品名（移除型号、颜色等）
            def simplify(text):
                # 移除括号内容
                import re
                text = re.sub(r'\([^)]*\)', '', text)
                text = re.sub(r'\[[^\]]*\]', '', text)
                # 移除数字和特殊字符
                text = re.sub(r'[0-9#\-_]', ' ', text)
                return ' '.join(text.split())
            
            order_simple = simplify(order_title)
            purchase_simple = simplify(purchase_name)
            
            # 计算相似度
            if asin_match:
                score = 100
            else:
                # token sort ratio 处理词序不同
                score = fuzz.token_sort_ratio(order_simple, purchase_simple)
                
                # 品牌匹配加分
                if order_brands and purchase_brands:
                    score += 10
            
            # 数量匹配检查
            if purchase_qty >= order_qty:
                score += 5
            
            if score > best_score and score >= 60:  # 阈值 60
                best_score = score
                best_match = purchase
        
        if best_match:
            # 插入匹配记录
            c.execute("""
                INSERT INTO purchase_order_links 
                (purchase_id, ebay_order_id, match_method, confidence, allocated_qty, allocated_cost_jpy, allocated_tax_jpy)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                best_match['id'],
                order_id,
                'smart_match',
                best_score / 100,
                order_qty,
                best_match['total_price_jpy'],
                best_match['tax_jpy']
            ))
            matched += 1
            print(f"✅ {order_id}: {best_match['item_name'][:40]} (相似度：{best_score})")
        else:
            unmatched_orders.append(order_id)
            print(f"❌ {order_id}: 未找到匹配")
    
    conn.commit()
    conn.close()
    
    print(f"\n✅ 匹配完成：{matched}/{len(orders)}")
    if unmatched_orders:
        print(f"⚠️ 未匹配订单：{len(unmatched_orders)}")

if __name__ == '__main__':
    match_products()
