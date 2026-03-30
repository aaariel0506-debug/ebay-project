#!/usr/bin/env python3
"""检查数据库状态"""
import sqlite3

DB_PATH = '/Users/arielhe/.openclaw/workspace/ebay-tax-system/data/orders.db'

conn = sqlite3.connect(DB_PATH)
conn.row_factory = sqlite3.Row
cursor = conn.cursor()

print("=== 数据库状态 ===\n")

# eBay 订单
cursor.execute("SELECT COUNT(*) as cnt FROM ebay_orders")
print(f"eBay 订单总数：{cursor.fetchone()['cnt']}")

cursor.execute("SELECT COUNT(*) as cnt FROM ebay_orders WHERE strftime('%Y-%m', sale_date) = '2026-02'")
print(f"2 月份订单数：{cursor.fetchone()['cnt']}")

# 采购记录
cursor.execute("SELECT COUNT(*) as cnt FROM purchases")
print(f"\n采购记录总数：{cursor.fetchone()['cnt']}")

# 快递记录
cursor.execute("SELECT COUNT(*) as cnt FROM shipments")
print(f"快递记录总数：{cursor.fetchone()['cnt']}")

# 匹配关系
cursor.execute("SELECT COUNT(*) as cnt FROM purchase_order_links")
print(f"采购 -订单匹配数：{cursor.fetchone()['cnt']}")

# 显示 2 月份订单详情
print("\n=== 2 月份订单详情 ===")
cursor.execute("""
    SELECT order_id, sale_date, item_title, sale_price_usd 
    FROM ebay_orders 
    WHERE strftime('%Y-%m', sale_date) = '2026-02'
    ORDER BY sale_date
""")
orders = cursor.fetchall()

if orders:
    for o in orders:
        print(f"  {o['order_id']} | {o['sale_date']} | {o['item_title'][:30]} | ${o['sale_price_usd']}")
else:
    print("  (无 2 月份订单数据)")

conn.close()
