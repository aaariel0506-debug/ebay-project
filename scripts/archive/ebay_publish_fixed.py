#!/usr/bin/env python3
"""
eBay Listing 发布 - 修复版本 v2
通过查询 SKU 获取 Offer ID
"""

import requests
import json
import time
from datetime import datetime

EBAY_API = "https://api.sandbox.ebay.com"

with open('ebay_config.json') as f:
    config = json.load(f)

USER_TOKEN = config.get('OAUTH_TOKEN', '')

def get_headers():
    return {
        'Authorization': f'Bearer {USER_TOKEN}',
        'Content-Type': 'application/json',
        'Content-Language': 'en-US',
        'X-EBAY-C-MARKETPLACE-ID': 'EBAY_US',
        'Accept': 'application/json'
    }

print("=" * 60)
print("🛒 eBay Listing 发布 - 修复版本 v2")
print("=" * 60)

# 生成 SKU
timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
sku = f"TEST{timestamp}"
print(f"\n使用 SKU: {sku}")

# 步骤 1: 创建 Inventory Item
print("\n" + "=" * 60)
print("步骤 1: 创建 Inventory Item")
print("=" * 60)

item_data = {
    "sku": sku,
    "locale": "en_US",
    "product": {
        "title": "Hobonichi 5-Year Techo Gift Edition 2026-2030",
        "aspects": {
            "Brand": ["Hobonichi"],
            "Type": ["Planner"]
        }
    }
}

resp = requests.put(
    f"{EBAY_API}/sell/inventory/v1/inventory_item/{sku}",
    headers=get_headers(),
    json=item_data
)

print(f"状态码：{resp.status_code}")
if resp.status_code not in [200, 201, 204]:
    print(f"❌ 失败：{resp.text[:200]}")
    exit(1)
print("✅ Inventory Item 创建成功！")

# 步骤 2: 创建 Offer
print("\n" + "=" * 60)
print("步骤 2: 创建 Offer")
print("=" * 60)

offer_data = {
    "sku": sku,
    "marketplaceId": "EBAY_US",
    "categoryId": "11450",
    "format": "FIXED_PRICE",
    "pricingSummary": {
        "minimumPrice": {
            "value": "0.99",
            "currency": "USD"
        }
    },
    "availability": {
        "shipToLocationAvailability": {
            "quantity": 1
        }
    }
}

resp = requests.post(
    f"{EBAY_API}/sell/inventory/v1/offer",
    headers=get_headers(),
    json=offer_data
)

print(f"状态码：{resp.status_code}")
if resp.status_code not in [200, 201]:
    print(f"❌ 失败：{resp.text[:300]}")
    exit(1)
print("✅ Offer 创建请求已发送")

# 等待同步
print("等待系统同步 (10 秒)...")
for i in range(10, 0, -1):
    print(f"  {i}...")
    time.sleep(1)

# 查询该 SKU 的 Offers
print("\n查询该 SKU 的 Offers...")
offer_id = None
for attempt in range(5):
    query_resp = requests.get(
        f"{EBAY_API}/sell/inventory/v1/offer?sku={sku}",
        headers=get_headers()
    )
    print(f"  尝试 {attempt + 1}/5: Status {query_resp.status_code}")
    
    if query_resp.status_code == 200:
        data = query_resp.json()
        offers = data.get('offers', [])
        if offers:
            offer_id = offers[0].get('offerId')
            print(f"  ✅ 找到 Offer ID: {offer_id}")
            break
        else:
            print(f"  暂无 Offers，等待...")
    elif query_resp.status_code == 404:
        print(f"  404 - Offer 尚未同步，等待...")
    else:
        print(f"  错误：{query_resp.text[:100]}")
    
    time.sleep(3)

if not offer_id:
    print("\n❌ 无法获取 Offer ID，但 Offer 可能已创建")
    print("请在 eBay 沙盒后台手动查看")
    exit(0)

# 步骤 3: 发布 Offer
print("\n" + "=" * 60)
print("步骤 3: 发布 Offer")
print("=" * 60)

print(f"发布 Offer: {offer_id}")
publish_resp = requests.post(
    f"{EBAY_API}/sell/inventory/v1/offer/{offer_id}/publish",
    headers=get_headers()
)

print(f"Publish Status: {publish_resp.status_code}")

if publish_resp.status_code in [200, 204]:
    print("✅ Listing 发布成功！")
    print(f"\n查看 Listing: https://www.sandbox.ebay.com/itm/{offer_id}")
else:
    print(f"响应：{publish_resp.text[:300]}")
    
    # 查询 Offer 状态
    print("\n查询 Offer 状态...")
    status_resp = requests.get(
        f"{EBAY_API}/sell/inventory/v1/offer/{offer_id}",
        headers=get_headers()
    )
    if status_resp.status_code == 200:
        status_data = status_resp.json()
        print(f"Offer 状态：{status_data.get('status', 'N/A')}")
        if status_data.get('status') == 'PUBLISHED':
            print("✅ Listing 已经发布！")
            print(f"查看 Listing: https://www.sandbox.ebay.com/itm/{offer_id}")

print("\n" + "=" * 60)
print("完成")
print("=" * 60)
