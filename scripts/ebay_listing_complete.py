#!/usr/bin/env python3
"""
eBay Listing 完整流程 - 可运行版本
已测试通过 Inventory Item 创建
"""

import requests
import json
import base64
import time
from datetime import datetime

EBAY_API = "https://api.sandbox.ebay.com"

with open('ebay_config.json') as f:
    config = json.load(f)

APP_ID = config.get('EBAY_APP_ID', '')
APP_SECRET = config.get('EBAY_APP_SECRET', '')
USER_TOKEN = config.get('OAUTH_TOKEN', '')

def get_headers():
    return {
        'Authorization': f'Bearer {USER_TOKEN}',
        'Content-Type': 'application/json',
        'X-EBAY-C-MARKETPLACE-ID': 'EBAY_US',
        'X-EBAY-C-ENDUSERCTX': f'appId={APP_ID}',
        'Accept': 'application/json',
        'Content-Language': 'en-US'
    }

def get_client_token():
    credentials = f"{APP_ID}:{APP_SECRET}"
    encoded = base64.b64encode(credentials.encode()).decode()
    
    resp = requests.post(
        f"{EBAY_API}/identity/v1/oauth2/token",
        headers={
            'Content-Type': 'application/x-www-form-urlencoded',
            'Authorization': f'Basic {encoded}'
        },
        data={'grant_type': 'client_credentials', 'scope': 'https://api.ebay.com/oauth/api_scope'}
    )
    
    return resp.json().get('access_token', '') if resp.status_code == 200 else None

print("=" * 60)
print("🛒 eBay Listing 完整流程")
print("=" * 60)

# 生成 SKU（只用字母数字）
timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
sku = f"TEST{timestamp}"
print(f"\n使用 SKU: {sku}（只包含字母数字）")

# 步骤 1: 创建 Inventory Item
print("\n" + "=" * 60)
print("步骤 1: 创建 Inventory Item")
print("=" * 60)

item_data = {
    "sku": sku,
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

# 等待一下让系统同步
time.sleep(2)

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

print("✅ Offer 创建成功！")

# 尝试从响应中获取 offer_id
offer_id = None
if resp.text:
    try:
        offer_id = resp.json().get('offerId')
    except:
        pass

if not offer_id:
    # 尝试从 Location 头获取
    location = resp.headers.get('Location', '')
    if location:
        offer_id = location.split('/')[-1]
    
    if not offer_id:
        # 等待并查询
        print("等待系统同步...")
        time.sleep(3)
        
        # 查询刚创建的 Offer
        print("查询 Offers...")
        query_resp = requests.get(
            f"{EBAY_API}/sell/inventory/v1/offer?sku={sku}",
            headers=get_headers()
        )
        
        if query_resp.status_code == 200 and query_resp.json().get('offers'):
            offer_id = query_resp.json()['offers'][0].get('offerId')

if not offer_id:
    print("⚠️  无法获取 Offer ID，但 Offer 已创建")
    print("请手动查询或稍后重试")
    exit(0)

print(f"Offer ID: {offer_id}")

# 步骤 3: 发布
print("\n" + "=" * 60)
print("步骤 3: 发布 Listing")
print("=" * 60)

pub_resp = requests.post(
    f"{EBAY_API}/sell/inventory/v1/offer/{offer_id}/publish",
    headers=get_headers()
)

print(f"状态码：{pub_resp.status_code}")

if pub_resp.status_code in [200, 201, 204]:
    print("\n🎉 成功！Listing 发布成功！")
    
    if pub_resp.text:
        try:
            listing_id = pub_resp.json().get('listingId')
            if listing_id:
                print(f"Listing ID: {listing_id}")
                print(f"查看：https://www.sandbox.ebay.com/itm/{listing_id}")
        except:
            pass
else:
    print(f"❌ 发布失败：{pub_resp.status_code}")
    print(f"{pub_resp.text[:300]}")

print("\n" + "=" * 60)
print("流程完成")
print("=" * 60)
