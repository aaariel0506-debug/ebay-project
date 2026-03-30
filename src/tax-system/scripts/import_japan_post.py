#!/usr/bin/env python3
"""
导入 Japan Post 运费数据并匹配到 eBay 订单
"""
import sqlite3
import openpyxl
from datetime import datetime

DB_PATH = '/Users/arielhe/.openclaw/workspace/ebay-tax-system/data/orders.db'
JP_POST_XLSX = '/Users/arielhe/.openclaw/media/inbound/db3dd780-68cb-40e1-88b9-62404f4f9896.xlsx'
EXCHANGE_RATE = 150.0

def import_japan_post():
    """导入 Japan Post 运费数据"""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
    # 创建 Japan Post 运费表
    c.execute("""
        CREATE TABLE IF NOT EXISTS japan_post_shipments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tracking_number TEXT UNIQUE,
            ship_date DATE,
            recipient TEXT,
            country TEXT,
            shipping_fee_jpy REAL,
            weight_g INTEGER,
            source_file TEXT,
            ebay_order_id TEXT,
            matched INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    # 清空旧数据
    c.execute("DELETE FROM japan_post_shipments")
    
    # 读取 Excel
    wb = openpyxl.load_workbook(JP_POST_XLSX)
    ws = wb.active
    
    imported = 0
    matched = 0
    
    for row in ws.iter_rows(min_row=2, values_only=True):
        if not row[0]:  # 跳过空行
            continue
        
        tracking = str(row[0]).strip()
        ship_date = row[1]
        recipient = row[2] or ''
        country = row[3] or ''
        fee_jpy = float(row[4]) if row[4] else 0
        weight_g = int(row[5]) if row[5] else 0
        source = row[6] or ''
        
        # 尝试匹配 eBay 订单
        c.execute("""
            SELECT order_id FROM ebay_orders 
            WHERE tracking_number = ?
        """, (tracking,))
        result = c.fetchone()
        ebay_order = result[0] if result else None
        
        if ebay_order:
            matched += 1
        
        c.execute("""
            INSERT INTO japan_post_shipments 
            (tracking_number, ship_date, recipient, country, shipping_fee_jpy, weight_g, source_file, ebay_order_id, matched)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (tracking, ship_date, recipient, country, fee_jpy, weight_g, source, ebay_order, 1 if ebay_order else 0))
        
        imported += 1
    
    conn.commit()
    conn.close()
    wb.close()
    
    print(f"✅ 导入 Japan Post 运单：{imported} 条")
    print(f"✅ 匹配到 eBay 订单：{matched} 条 ({matched/imported*100:.0f}%)")
    return imported, matched

def update_report():
    """更新报表，加入运费成本"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    
    # 统计运费
    c.execute("""
        SELECT SUM(shipping_fee_jpy) as total_fee, COUNT(*) as cnt
        FROM japan_post_shipments
        WHERE matched = 1
    """)
    r = c.fetchone()
    matched_shipping_jpy = r['total_fee'] or 0
    matched_count = r['cnt'] or 0
    
    matched_shipping_usd = matched_shipping_jpy / EXCHANGE_RATE
    
    # 统计 eBay 订单运费收入
    c.execute("""
        SELECT SUM(shipping_charged_usd) as total
        FROM ebay_orders
        WHERE strftime('%Y-%m', sale_date) = '2026-02'
    """)
    shipping_income = c.fetchone()['total'] or 0
    
    # 统计销售
    c.execute("""
        SELECT COUNT(*) as cnt, SUM(sale_price_usd) as sales
        FROM ebay_orders
        WHERE strftime('%Y-%m', sale_date) = '2026-02'
    """)
    s = c.fetchone()
    orders = s['cnt']
    sales = s['sales'] or 0
    
    # 统计采购成本
    c.execute("""
        SELECT SUM(allocated_cost_jpy) as cost
        FROM purchase_order_links
    """)
    purchase_cost_jpy = c.fetchone()['cost'] or 0
    purchase_cost_usd = purchase_cost_jpy / EXCHANGE_RATE
    
    # 计算利润（包含运费成本）
    # 利润 = 销售 + 运费收入 - 采购成本 - 运费成本
    gross_profit = sales + shipping_income - purchase_cost_usd - matched_shipping_usd
    
    conn.close()
    
    print(f"\n{'='*60}")
    print(f"📊 2026 年 2 月完整成本核算")
    print(f"{'='*60}")
    print(f"  订单数量：{orders}")
    print(f"  销售总额：${sales:.2f}")
    print(f"  运费收入：${shipping_income:.2f}")
    print(f"  销售 + 运费合计：${sales + shipping_income:.2f}")
    print(f"")
    print(f"  采购成本：¥{purchase_cost_jpy:,.0f} (${purchase_cost_usd:.2f})")
    print(f"  Japan Post 运费：¥{matched_shipping_jpy:,.0f} (${matched_shipping_usd:.2f})")
    print(f"  总成本：¥{purchase_cost_jpy + matched_shipping_jpy:,.0f} (${purchase_cost_usd + matched_shipping_usd:.2f})")
    print(f"")
    print(f"  💰 毛利润：${gross_profit:.2f}")
    print(f"  利润率：{gross_profit / (sales + shipping_income) * 100:.1f}%")
    print(f"{'='*60}")
    
    return {
        'orders': orders,
        'sales': sales,
        'shipping_income': shipping_income,
        'purchase_cost_jpy': purchase_cost_jpy,
        'purchase_cost_usd': purchase_cost_usd,
        'shipping_cost_jpy': matched_shipping_jpy,
        'shipping_cost_usd': matched_shipping_usd,
        'gross_profit': gross_profit,
        'match_rate': matched_count / orders * 100 if orders > 0 else 0
    }

if __name__ == '__main__':
    print("🚀 导入 Japan Post 运费数据...\n")
    imported, matched = import_japan_post()
    print("\n📊 更新成本核算...")
    stats = update_report()
    print("\n✅ 完成！")
