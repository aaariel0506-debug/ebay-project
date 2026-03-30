#!/usr/bin/env python3
import csv

print("=== 检查 eBay CSV ===")
with open('/Users/arielhe/.openclaw/media/inbound/3e653725-419e-4e22-a37b-3cc75cb97bf3.csv', 'r') as f:
    lines = [l for l in f.readlines() if l.strip()]
    print(f"有效行数：{len(lines)}")
    
    header = list(csv.reader([lines[0]]))[0]
    print(f"\n表头列数：{len(header)}")
    for i, col in enumerate(header[:60]):
        if 'Sale' in col or 'Date' in col or 'Order' in col:
            print(f"  列{i}: {col}")
    
    row = list(csv.reader([lines[3]]))[0]
    print(f"\n第一条数据:")
    print(f"  Order Number (列 1): {row[1]}")
    print(f"  Sale Date (列 49): {row[49] if len(row) > 49 else 'N/A'}")
    
    # 数 2 月份订单
    feb_count = 0
    for line in lines[3:]:
        row = list(csv.reader([line]))[0]
        if len(row) > 49 and 'Feb' in row[49]:
            feb_count += 1
    print(f"\n2 月份订单数：{feb_count}")

print("\n=== 检查 Amazon CSV ===")
with open('/Users/arielhe/.openclaw/media/inbound/de0d77eb-a9ce-404a-a815-bf97f1cbab5b.csv', 'r') as f:
    feb = 0
    total = 0
    for line in f:
        if '2026/02/' in line:
            feb += 1
        if '注文日' not in line and line.strip():
            total += 1
    print(f"总采购数：{total}")
    print(f"2 月份采购：{feb}")
