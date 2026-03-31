#!/usr/bin/env python3
"""
eBay Listing 发布 - v3
使用纯字母数字 SKU + 重试机制
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
print("🛒 eBay Listing 发布 - v3")
print("=" * 60)

# 生成纯字母数字 SKU（无连字符）
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
if resp.status_code == 201:
    print("✅ Offer 创建成功！")
    
    # 检查响应头和内容
    location = resp.headers.get('Location', '')
    print(f"Location Header: {location if location else 'N/A'}")
    
    # 尝试从响应体解析 offerId
    try:
        body = resp.json()
        offer_id = body.get('offerId', '')
        if offer_id:
            print(f"✅ 从响应体获取 Offer ID: {offer_id}")
        else:
            print("⚠️  响应体无 offerId")
            offer_id = ''
    except:
        offer_id = ''
        print("⚠️  无法解析响应体")
    
    # 如果还是没有 offer_id，从 Location 头提取
    if not offer_id and location:
        offer_id = location.split('/')[-1]
        print(f"✅ 从 Location 头提取 Offer ID: {offer_id}")
    
    if offer_id:
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
            print("✅✅✅ Listing 发布成功！")
            print(f"\n📦 查看 Listing: https://www.sandbox.ebay.com/itm/{offer_id}")
        else:
            print(f"发布响应：{publish_resp.text[:300]}")
            
            # 检查是否已经发布
            print("\n检查 Offer 状态...")
            status_resp = requests.get(
                f"{EBAY_API}/sell/inventory/v1/offer/{offer_id}",
                headers=get_headers()
            )
            if status_resp.status_code == 200:
                status = status_resp.json().get('status', 'N/A')
                print(f"Offer 状态：{status}")
                if status == 'PUBLISHED':
                    print("✅ Listing 已经发布！")
                    print(f"📦 https://www.sandbox.ebay.com/itm/{offer_id}")
    else:
        print("\n⚠️  无法获取 Offer ID")
        print("eBay 沙盒可能未返回完整响应")
        print("请等待几分钟后在 eBay 沙盒后台查看")
else:
    print(f"❌ 失败：{resp.text[:300]}")

print("\n" + "=" * 60)
print("完成")
print("=" * 60)
