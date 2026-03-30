"""
generator/folder_builder.py — 构建订单文件夹结构

为每个 eBay 订单创建文件夹结构，包含 HTML 页面和空文件夹供手动放置凭证。
"""
import os
from pathlib import Path
from db.db import fetch_all
from generator.html_order_page import generate_order_detail, generate_order_receipt


def build_order_folders(year: int, output_base: str, month: int | None = None) -> int:
    """
    为每个该年（和可选月份）的 eBay 订单创建文件夹结构

    文件夹结构：
        全年模式：{output_base}/orders/{order_id}/
        月份模式：{output_base}/orders_{year}-{month:02d}/{order_id}/
            01_order_detail.html
            02_order_receipt.html
            03_shipping_label/       ← 空文件夹，供手动放快递面单
            04_cpass_transaction/    ← 空文件夹，供手动放 CPass PDF
            05_japanpost_email/      ← 空文件夹，供手动放 Japan Post 截图
            README.txt               ← 说明本文件夹用途和手动操作步骤

    Args:
        year: 报税年份
        output_base: 输出基础目录
        month: 月份 1-12；None 表示全年

    Returns:
        生成的文件夹数量
    """
    # 获取指定年份（和可选月份）的 eBay 订单
    if month is not None:
        month_padded = f"{month:02d}"
        orders = fetch_all("""
            SELECT order_id FROM ebay_orders
            WHERE strftime('%Y', sale_date) = ?
              AND strftime('%m', sale_date) = ?
            ORDER BY sale_date
        """, (str(year), month_padded))
        orders_dir = Path(output_base) / f"orders_{year}-{month_padded}"
    else:
        orders = fetch_all("""
            SELECT order_id FROM ebay_orders
            WHERE strftime('%Y', sale_date) = ?
            ORDER BY sale_date
        """, (str(year),))
        orders_dir = Path(output_base) / "orders"

    if not orders:
        return 0

    # 创建 orders 基础目录
    orders_dir.mkdir(parents=True, exist_ok=True)

    folder_count = 0

    for order in orders:
        order_id = order['order_id']
        order_folder = orders_dir / order_id

        # 创建文件夹结构
        order_folder.mkdir(exist_ok=True)

        # 创建空文件夹
        (order_folder / "03_shipping_label").mkdir(exist_ok=True)
        (order_folder / "04_cpass_transaction").mkdir(exist_ok=True)
        (order_folder / "05_japanpost_email").mkdir(exist_ok=True)

        # 生成 HTML 文件
        detail_path = order_folder / "01_order_detail.html"
        receipt_path = order_folder / "02_order_receipt.html"

        try:
            generate_order_detail(order_id, str(detail_path))
            generate_order_receipt(order_id, str(receipt_path))
        except ValueError as e:
            # 订单数据不存在，跳过
            print(f"Warning: Skipping order {order_id}: {e}")
            continue

        # 生成 README.txt
        readme_path = order_folder / "README.txt"
        readme_content = f"""Order Documentation Folder
==========================

Order ID: {order_id}

This folder contains documentation and supporting documents for the above eBay order.

Folder Structure:
-----------------
01_order_detail.html      - Order detail page (generated from database)
02_order_receipt.html     - Order receipt for printing (generated from database)
03_shipping_label/        - Place shipping label PDFs here manually
04_cpass_transaction/     - Place CPass transaction PDFs here manually
05_japanpost_email/       - Place Japan Post email screenshots here manually

Manual Steps Required:
----------------------
1. Download the shipping label from your carrier's website
   → Save to: 03_shipping_label/

2. If using CPass, download the transaction receipt
   → Save to: 04_cpass_transaction/

3. If using Japan Post, save the email confirmation screenshot
   → Save to: 05_japanpost_email/

4. For Amazon Japan purchases, download the order receipt PDF
   → Save to: 04_cpass_transaction/ (or create a new folder)

Generated: {__import__('datetime').datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
"""

        readme_path.write_text(readme_content, encoding='utf-8')

        folder_count += 1

    return folder_count
