#!/usr/bin/env python3
"""
eBay Listing 发布 - 简化版本
专注于核心功能，减少必填字段
"""

import requests
import json
import base64
from pathlib import Path
from datetime import datetime

SCRIPT_DIR = Path(__file__).parent
CONFIG_FILE = SCRIPT_DIR / "ebay_config.json"

with open(CONFIG_FILE, 'r') as f:
    config = json.load(f)

EBAY_SANDBOX_API = "https://api.sandbox.ebay.com"
APP_ID = config.get('EBAY_APP_ID', '')
APP_SECRET = config.get('EBAY_APP_SECRET', '')
USER_TOKEN = config.get('OAUTH_TOKEN', '')

print("=" * 60)
print("🛒 eBay Listing 发布 - 简化版")
print("=" * 60)

# 生成唯一 SKU
sku = f"TEST-{datetime.now().strftime('%Y%m%d%H%M%S')}"
print(f"\n使用 SKU: {sku}")

# ============== 步骤 1: 创建 Inventory Item ==============
print("\n" + "=" * 60)
print("步骤 1: 创建库存商品 (Inventory Item)")
print("=" * 60)

item_data = {
    "sku": sku,
    "product": {
        "title": "Hobonichi 5-Year Techo Gift Edition 2026-2030",
        "aspects": {
            "Brand": ["Hobonichi"]
        }
    }
}

credentials = f"{APP_ID}:{APP_SECRET}"
encoded = base64.b64encode(credentials.encode()).decode()

# 先获取 Client Token
token_response = requests.post(
    f"{EBAY_SANDBOX_API}/identity/v1/oauth2/token",
    headers={
        'Content-Type': 'application/x-www-form-urlencoded',
        'Authorization': f'Basic {encoded}'
    },
    data={
        'grant_type': 'client_credentials',
        'scope': 'https://api.ebay.com/oauth/api_scope'
    }
)

if token_response.status_code == 200:
    client_token = token_response.json().get('access_token', '')
    print(f"✓ Client Token 获取成功")
else:
    print(f"❌ Client Token 失败：{token_response.status_code}")
    client_token = None

if client_token:
    # 创建 Inventory Item
    item_url = f"{EBAY_SANDBOX_API}/sell/inventory/v1/inventory_item/{sku}"
    
    item_response = requests.put(
        item_url,
        headers={
            'Authorization': f'Bearer {USER_TOKEN}',
            'Content-Type': 'application/json',
            'X-EBAY-C-MARKETPLACE-ID': 'EBAY_US',
            'X-EBAY-C-ENDUSERCTX': f'appId={APP_ID}'
        },
        json=item_data
    )
    
    print(f"响应状态码：{item_response.status_code}")
    
    if item_response.status_code in [200, 201, 204]:
        print("✅ Inventory Item 创建成功！")
        
        # ============== 步骤 2: 创建 Offer ==============
        print("\n" + "=" * 60)
        print("步骤 2: 创建报价 (Offer)")
        print("=" * 60)
        
        offer_data = {
            "sku": sku,
            "marketplaceId": "EBAY_US",
            "categoryId": "11450",
            "pricingSummary": {
                "minimumPrice": {
                    "value": "189.00",
                    "currency": "USD"
                }
            },
            "availability": {
                "shipToLocationAvailability": {
                    "quantity": 1
                }
            }
        }
        
        offer_url = f"{EBAY_SANDBOX_API}/sell/inventory/v1/offer"
        
        offer_response = requests.post(
            offer_url,
            headers={
                'Authorization': f'Bearer {USER_TOKEN}',
                'Content-Type': 'application/json',
                'X-EBAY-C-MARKETPLACE-ID': 'EBAY_US',
                'X-EBAY-C-ENDUSERCTX': f'appId={APP_ID}'
            },
            json=offer_data
        )
        
        print(f"响应状态码：{offer_response.status_code}")
        
        if offer_response.status_code in [200, 201]:
            offer_id = offer_response.json().get('offerId', '')
            print(f"✅ Offer 创建成功！")
            print(f"   Offer ID: {offer_id}")
            
            # ============== 步骤 3: 发布 ==============
            print("\n" + "=" * 60)
            print("步骤 3: 发布 Listing")
            print("=" * 60)
            
            publish_url = f"{EBAY_SANDBOX_API}/sell/inventory/v1/offer/{offer_id}/publish"
            
            publish_response = requests.post(
                publish_url,
                headers={
                    'Authorization': f'Bearer {USER_TOKEN}',
                    'Content-Type': 'application/json',
                    'X-EBAY-C-MARKETPLACE-ID': 'EBAY_US'
                }
            )
            
            print(f"响应状态码：{publish_response.status_code}")
            
            if publish_response.status_code in [200, 201, 204]:
                print("\n🎉 成功！Listing 已发布！")
                
                if publish_response.json():
                    listing_id = publish_response.json().get('listingId', '')
                    if listing_id:
                        print(f"Listing ID: {listing_id}")
                        print(f"查看：https://www.sandbox.ebay.com/itm/{listing_id}")
            else:
                print(f"\n⚠️  发布失败：{publish_response.status_code}")
                print(f"响应：{publish_response.text[:300]}")
        else:
            print(f"❌ Offer 创建失败：{offer_response.status_code}")
            print(f"响应：{offer_response.text[:300]}")
    else:
        print(f"❌ Inventory Item 创建失败：{item_response.status_code}")
        print(f"响应：{item_response.text[:300]}")

print("\n" + "=" * 60)
print("测试完成")
print("=" * 60)
