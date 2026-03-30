#!/usr/bin/env python3
"""
eBay publish_by_inventory_item API 测试
通过 SKU 直接发布，不需要 offerId
"""

import requests
import json
import time
from datetime import datetime

with open('ebay_config.json') as f:
    config = json.load(f)

USER_TOKEN = config.get('OAUTH_TOKEN', '')

EBAY_API = "https://api.sandbox.ebay.com"

def get_headers():
    return {
        'Authorization': f'Bearer {USER_TOKEN}',
        'Content-Type': 'application/json',
        'Content-Language': 'en-US',
        'X-EBAY-C-MARKETPLACE-ID': 'EBAY_US',
        'Accept': 'application/json'
    }

print("=" * 60)
print("🛒 eBay publish_by_inventory_item 测试")
print("=" * 60)

# 生成 SKU
timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
sku = f"PBYSKU{timestamp}"
print(f"\n使用 SKU: {sku}")

# 步骤 1: 创建 Inventory Item
print("\n" + "=" * 60)
print("步骤 1: 创建 Inventory Item")
print("=" * 60)

item_data = {
    "sku": sku,
    "locale": "en_US",
    "product": {
        "title": "Test Product - Hobonichi Techo",
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

print(f"Status: {resp.status_code}")
if resp.status_code not in [200, 201, 204]:
    print(f"❌ 失败：{resp.text[:200]}")
    exit(1)
print("✅ Inventory Item 创建成功")

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
        "price": {
            "value": "10.00",
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

print(f"Status: {resp.status_code}")
if resp.status_code != 201:
    print(f"❌ 失败：{resp.text[:200]}")
    exit(1)
print("✅ Offer 创建成功")

# 等待同步
print("\n等待 5 秒...")
time.sleep(5)

# 步骤 3: 尝试通过 SKU 发布
print("\n" + "=" * 60)
print("步骤 3: 通过 SKU 发布 Listing")
print("=" * 60)

# 尝试多个可能的 API
publish_endpoints = [
    f"/sell/inventory/v1/inventory_item/{sku}/publish_by_inventory_item",
    f"/sell/inventory/v1/publish_by_inventory_item",
    f"/sell/inventory/v1/listing/{sku}/publish",
]

for endpoint in publish_endpoints:
    print(f"\n尝试：{endpoint}")
    
    resp = requests.post(
        f"{EBAY_API}{endpoint}",
        headers=get_headers(),
        json={"marketplaceId": "EBAY_US"}
    )
    
    print(f"Status: {resp.status_code}")
    
    if resp.status_code in [200, 204]:
        print("✅ 发布成功！")
        break
    elif resp.status_code == 404:
        print("❌ 端点不存在")
    else:
        print(f"响应：{resp.text[:300]}")

print("\n" + "=" * 60)

# 步骤 4: 查询 Listing 状态
print("\n查询 Listing 状态...")
resp = requests.get(
    f"{EBAY_API}/sell/inventory/v1/listing?sku={sku}",
    headers=get_headers()
)
print(f"Status: {resp.status_code}")
if resp.status_code == 200:
    data = resp.json()
    print(json.dumps(data, indent=2)[:1000])
else:
    print(f"响应：{resp.text[:300]}")

print("\n" + "=" * 60)
