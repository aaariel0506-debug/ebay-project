#!/usr/bin/env python3
"""
更新 Japan Post 运费到报表
- 读取 2月JP运单详情.xlsx
- 按追踪号匹配到 tax_report_2026-02_FINAL.xlsx
- 日元运费转换为美元（汇率 150 JPY/USD）
- 生成更新后的报表
"""

import pandas as pd
import os
from datetime import datetime

# 配置
JP_FILE = 'data/input/2月JP运单详情.xlsx'
REPORT_FILE = 'data/outputs/2026-02/tax_report_2026-02_FINAL.xlsx'
OUTPUT_FILE = 'data/outputs/2026-02/tax_report_2026-02_v2.xlsx'
EXCHANGE_RATE = 150  # JPY/USD

def main():
    print("=" * 60)
    print("Japan Post 运费更新工具")
    print("=" * 60)
    
    # 1. 读取 Japan Post 运单数据
    print(f"\n1. 读取 Japan Post 运单: {JP_FILE}")
    jp_df = pd.read_excel(JP_FILE)
    print(f"   - 共 {len(jp_df)} 条运单记录")
    print(f"   - 列名: {list(jp_df.columns)}")
    
    # 创建追踪号到运费的映射（日元）
    jp_shipping_map = {}
    for _, row in jp_df.iterrows():
        tracking = str(row['快递单号']).strip()
        cost_jpy = float(row['运费(円)'])
        jp_shipping_map[tracking] = cost_jpy
    
    print(f"   - 追踪号映射: {len(jp_shipping_map)} 条")
    
    # 2. 读取现有报表
    print(f"\n2. 读取现有报表: {REPORT_FILE}")
    xlsx = pd.ExcelFile(REPORT_FILE)
    print(f"   - Sheets: {xlsx.sheet_names}")
    
    # 读取各 sheet
    summary_df = pd.read_excel(xlsx, '财务摘要')
    orders_df = pd.read_excel(xlsx, '订单明细')
    purchase_df = pd.read_excel(xlsx, '采购记录（2月）')
    match_df = pd.read_excel(xlsx, '匹配详情')
    
    print(f"   - 订单数量: {len(orders_df)}")
    
    # 3. 匹配并更新运费
    print(f"\n3. 匹配追踪号并更新运费")
    print(f"   - 汇率: {EXCHANGE_RATE} JPY/USD")
    
    updated_count = 0
    matched_tracking = []
    
    for idx, row in orders_df.iterrows():
        tracking = str(row['追踪号']) if pd.notna(row['追踪号']) else ''
        
        # 检查是否是 Japan Post 追踪号
        if tracking and (tracking.startswith('LX') or tracking.startswith('LP')):
            if tracking in jp_shipping_map:
                cost_jpy = jp_shipping_map[tracking]
                cost_usd = round(cost_jpy / EXCHANGE_RATE, 2)
                
                # 更新运费（从买家支付的运费改为实际 Japan Post 成本）
                old_shipping = orders_df.at[idx, '运费 USD']
                orders_df.at[idx, '运费 USD'] = cost_usd
                
                # 重新计算毛利润
                price = row['售价 USD'] if pd.notna(row['售价 USD']) else 0
                purchase_cost = row['采购成本 USD'] if pd.notna(row['采购成本 USD']) else 0
                ebay_fee = price * 0.15  # 假设 15% eBay 费用
                
                new_profit = round(price - purchase_cost - cost_usd - ebay_fee, 2)
                orders_df.at[idx, '毛利润 USD'] = new_profit
                
                matched_tracking.append({
                    'eBay 订单号': row['eBay 订单号'],
                    '追踪号': tracking,
                    '原运费 USD': old_shipping,
                    '新运费 USD': cost_usd,
                    '运费 JPY': cost_jpy,
                    '更新后毛利润': new_profit
                })
                updated_count += 1
    
    print(f"   - 匹配并更新: {updated_count} 条订单")
    
    # 4. 显示匹配详情
    if matched_tracking:
        print(f"\n4. 匹配详情:")
        match_summary = pd.DataFrame(matched_tracking)
        print(match_summary.to_string(index=False))
        
        # 保存匹配详情
        match_detail_file = 'data/outputs/2026-02/jp_shipping_update_detail.csv'
        match_summary.to_csv(match_detail_file, index=False)
        print(f"\n   - 匹配详情已保存: {match_detail_file}")
    
    # 5. 更新财务摘要
    print(f"\n5. 更新财务摘要")
    
    # 重新计算汇总数据
    total_revenue = orders_df['售价 USD'].sum()
    total_shipping = orders_df['运费 USD'].sum()
    total_purchase = orders_df['采购成本 USD'].sum()
    total_profit = orders_df['毛利润 USD'].sum()
    
    # 更新摘要（假设摘要在第一行）
    if len(summary_df) > 0:
        summary_df.at[0, '销售收入 USD'] = total_revenue
        summary_df.at[0, '运费收入 USD'] = total_shipping
        summary_df.at[0, '采购成本 USD'] = total_purchase
        summary_df.at[0, '毛利润 USD'] = total_profit
    
    print(f"   - 销售收入: ${total_revenue:,.2f}")
    print(f"   - 运费: ${total_shipping:,.2f}")
    print(f"   - 采购成本: ${total_purchase:,.2f}")
    print(f"   - 毛利润: ${total_profit:,.2f}")
    
    # 6. 保存更新后的报表
    print(f"\n6. 保存更新后的报表: {OUTPUT_FILE}")
    
    with pd.ExcelWriter(OUTPUT_FILE, engine='openpyxl') as writer:
        summary_df.to_excel(writer, sheet_name='财务摘要', index=False)
        orders_df.to_excel(writer, sheet_name='订单明细', index=False)
        purchase_df.to_excel(writer, sheet_name='采购记录（2月）', index=False)
        match_df.to_excel(writer, sheet_name='匹配详情', index=False)
    
    print(f"\n✅ 完成！报表已更新")
    print(f"   - 原报表: {REPORT_FILE}")
    print(f"   - 新报表: {OUTPUT_FILE}")
    
    return updated_count

if __name__ == '__main__':
    main()
