#!/usr/bin/env python3
"""
eBay Sell API createListing 调用
一步完成 Listing 发布
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

print("=" * 60)
print("🛒 eBay Sell API createListing 测试")
print("=" * 60)

# 简化的 Listing 数据
listing_data = {
    "title": "Test Product - Hobonichi Techo",
    "subtitle": "5-Year Planner",
    "categoryId": "11450",
    "description": "<p>Test product description</p>",
    "price": {
        "value": "10.00",
        "currency": "USD"
    },
    "quantity": 1,
    "condition": "NEW",
    "format": "FIXED_PRICE",
    "listingDuration": "DAYS_7",
    "paymentMethods": ["MANAGED_PAYMENT"],
    "shipToLocations": {
        "offered": ["US"]
    },
    "shippingOptions": [
        {
            "shippingService": "USPS_FIRST_CLASS",
            "shippingCost": {
                "value": "3.99",
                "currency": "USD"
            },
            "shipToLocations": ["US"]
        }
    ],
    "returnPolicy": {
        "returnsAccepted": False
    }
}

print("\n发送 createListing 请求...")
print(f"标题：{listing_data['title']}")
print(f"价格：${listing_data['price']['value']}")

resp = requests.post(
    f"{EBAY_API}/sell/listing/v1/listing",
    headers=get_headers(),
    json=listing_data
)

print(f"\n响应状态码：{resp.status_code}")
print(f"\n响应内容：")
print(resp.text[:1000])

if resp.status_code in [200, 201]:
    try:
        data = resp.json()
        listing_id = data.get('listingId', '')
        draft_id = data.get('draftId', '')
        print(f"\n✅ 请求成功！")
        if listing_id:
            print(f"Listing ID: {listing_id}")
            print(f"查看：https://www.sandbox.ebay.com/itm/{listing_id}")
        if draft_id:
            print(f"Draft ID: {draft_id}")
    except:
        print("无法解析响应")
else:
    print("\n❌ 失败")

print("\n" + "=" * 60)
