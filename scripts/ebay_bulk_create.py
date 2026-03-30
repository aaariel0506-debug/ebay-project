#!/usr/bin/env python3
"""
eBay bulk_create_listing API 测试
尝试多个 API 端点
"""

import requests
import json
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

# 生成 SKU
timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
sku = f"BULK{timestamp}"

# Listing 数据
listing_data = {
    "listings": [
        {
            "sku": sku,
            "offers": [
                {
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
            ],
            "product": {
                "title": "Test Product - Hobonichi Techo",
                "aspects": {
                    "Brand": ["Hobonichi"],
                    "Type": ["Planner"]
                }
            }
        }
    ]
}

# 尝试多个 API 端点
endpoints = [
    "/sell/inventory/v1/bulk_create_or_replace_listing",
    "/sell/inventory/v1/bulk_create_listing",
    "/sell/listing/v1/bulk_create_listing",
    "/sell/inventory/v1/listing",
]

print("=" * 60)
print("🛒 eBay Bulk Create API 测试 - 多端点")
print("=" * 60)
print(f"\nSKU: {sku}")

for endpoint in endpoints:
    print(f"\n{'='*50}")
    print(f"尝试：{endpoint}")
    print('='*50)
    
    resp = requests.post(
        f"{EBAY_API}{endpoint}",
        headers=get_headers(),
        json=listing_data
    )
    
    print(f"Status: {resp.status_code}")
    
    if resp.status_code == 404:
        print("❌ 端点不存在")
    elif resp.status_code in [200, 201, 207]:
        print("✅ 成功！")
        try:
            data = resp.json()
            print(json.dumps(data, indent=2)[:1000])
            
            # 提取 listingId
            if 'results' in data:
                for result in data['results']:
                    listing_id = result.get('listingId')
                    if listing_id:
                        print(f"\n🎉 Listing ID: {listing_id}")
                        print(f"查看：https://www.sandbox.ebay.com/itm/{listing_id}")
                        break
        except:
            print(resp.text[:500])
        break
    else:
        print(f"❌ 错误：{resp.text[:300]}")

print("\n" + "=" * 60)
