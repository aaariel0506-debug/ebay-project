#!/usr/bin/env python3
"""
eBay 完整 Listing 发布流程脚本
包含 5 个步骤：
1. 创建库存位置 (Inventory Location)
2. 创建业务政策 (Business Policies)
3. 创建库存商品 (Inventory Item)
4. 创建销售报价 (Create Offer)
5. 正式发布 (Publish Offer)

运行方式：python3 ebay_full_listing_workflow.py
"""

import requests
import json
import base64
from pathlib import Path
from datetime import datetime

# ============== 配置 ==============
SCRIPT_DIR = Path(__file__).parent
CONFIG_FILE = SCRIPT_DIR / "ebay_config.json"

with open(CONFIG_FILE, 'r') as f:
    config = json.load(f)

# API 配置
EBAY_SANDBOX_API = "https://api.sandbox.ebay.com"
APP_ID = config.get('EBAY_APP_ID', '')
APP_SECRET = config.get('EBAY_APP_SECRET', '')
USER_TOKEN = config.get('OAUTH_TOKEN', '')

# 测试产品信息
TEST_PRODUCT = {
    "sku": f"HOBO-HACONIWA-{datetime.now().strftime('%Y%m%d%H%M%S')}",
    "title": "Hobonichi 5-Year Techo Gift Edition 2026-2030 haconiwa iyo okumi Limited Planner",
    "price": 189.00,
    "quantity": 3,
    "category": "11450",  # Books (沙盒可用分类)
    "condition": "1000",  # New
    "description": """
<h2>Hobonichi 5-Year Techo Gift Edition - haconiwa (2026-2030)</h2>
<p>Designed by Embroidery Artist iyo okumi | Limited Gift Edition</p>
<div style="background:#f5f9f5; padding:15px; border-left:4px solid #2c5530;">
<strong>✨ Special Limited Edition</strong> - Miniature garden themed 5-year planner.
</div>
<h3>Highlights:</h3>
<ul>
<li>Exclusive haconiwa Design by iyo okumi</li>
<li>5-Year Planning (2026-2030)</li>
<li>Premium Embroidered Cover</li>
<li>752 pages Tomoe River paper</li>
</ul>
<p style="color:red;"><strong>⚠️ TEST Listing - Sandbox Environment</strong></p>
""",
    "image_url": "https://via.placeholder.com/1600x1600?text=Hobonichi+haconiwa"
}

# ============== 工具函数 ==============
def get_client_token():
    """获取 Client Token"""
    credentials = f"{APP_ID}:{APP_SECRET}"
    encoded = base64.b64encode(credentials.encode()).decode()
    
    response = requests.post(
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
    
    if response.status_code == 200:
        return response.json().get('access_token', '')
    else:
        print(f"❌ Client Token 获取失败：{response.status_code}")
        return None

def make_request(method, url, data=None, use_user_token=True):
    """发送 API 请求"""
    token = USER_TOKEN if use_user_token else get_client_token()
    
    headers = {
        'Authorization': f'Bearer {token}',
        'Content-Type': 'application/json',
        'X-EBAY-C-MARKETPLACE-ID': 'EBAY_US',
        'X-EBAY-C-ENDUSERCTX': f'appId={APP_ID}',
        'Content-Language': 'en-US'
    }
    
    if method == 'GET':
        response = requests.get(url, headers=headers, timeout=30)
    elif method == 'POST':
        response = requests.post(url, headers=headers, json=data, timeout=30)
    elif method == 'PUT':
        response = requests.put(url, headers=headers, json=data, timeout=30)
    else:
        return None
    
    return {
        'status': response.status_code,
        'data': response.json() if response.text else None,
        'text': response.text
    }

# ============== 步骤 1: 创建库存位置 ==============
def step1_create_location():
    """创建库存位置（仓库）"""
    print("\n" + "=" * 60)
    print("步骤 1: 创建库存位置 (Inventory Location)")
    print("=" * 60)
    
    location_key = "TEST_WAREHOUSE_01"
    
    location_data = {
        "location": {
            "address": {
                "addressLine1": "1-2-3 Shibuya",
                "city": "Tokyo",
                "countryCode": "JP",
                "postalCode": "150-0001",
                "stateOrProvince": "Tokyo"
            },
            "locationName": "Test Warehouse Tokyo",
            "locationTypes": ["WAREHOUSE"],
            "phone": {
                "countryCode": "81",
                "phoneNumber": "312345678"
            },
            "accessCode": "TEST123",
            "defaultShippingAddress": True
        },
        "merchantLocationKey": location_key
    }
    
    url = f"{EBAY_SANDBOX_API}/sell/inventory/v1/location/{location_key}"
    
    print(f"创建仓库：{location_key}")
    print(f"地址：1-2-3 Shibuya, Tokyo, Japan")
    
    result = make_request('PUT', url, location_data)
    
    if result['status'] in [200, 201, 204]:
        print("✅ 库存位置创建成功！")
        return location_key
    elif result['status'] == 409:
        print("⚠️  仓库已存在，继续使用")
        return location_key
    else:
        print(f"❌ 创建失败：{result['status']}")
        print(f"   {result['text'][:200]}")
        return None

# ============== 步骤 2: 创建业务政策 ==============
def step2_create_policies():
    """创建三大业务政策"""
    print("\n" + "=" * 60)
    print("步骤 2: 创建业务政策 (Business Policies)")
    print("=" * 60)
    
    policies = {}
    
    # 2.1 付款政策
    print("\n2.1 创建付款政策...")
    payment_policy = {
        "name": f"Test Payment Policy {datetime.now().strftime('%Y%m%d%H%M%S')}",
        "description": "Payment policy for test listings",
        "categoryType": "MARKETPLACE",
        "paymentMethods": ["PAYPAL", "CREDIT_CARD"],
        "immediatePay": False
    }
    
    url = f"{EBAY_SANDBOX_API}/sell/fulfillment/v1/payment_policy"
    result = make_request('POST', url, payment_policy, use_user_token=True)
    
    if result['status'] in [200, 201]:
        policy_id = result['data'].get('paymentPolicyId', '')
        print(f"✅ 付款政策创建成功：{policy_id}")
        policies['payment'] = policy_id
    else:
        print(f"⚠️  付款政策创建失败：{result['status']}")
        policies['payment'] = None
    
    # 2.2 物流政策
    print("\n2.2 创建物流政策...")
    fulfillment_policy = {
        "name": f"Test Shipping Policy {datetime.now().strftime('%Y%m%d%H%M%S')}",
        "description": "Shipping from Japan via EMS",
        "categoryType": "MARKETPLACE",
        "fulfillmentPolicyType": "SHIP_TO_HOME",
        "shippingCarrierCode": "JAPAN_POST",
        "shippingServiceCode": "JP_EMS",
        "shippingCostType": "FLAT",
        "shippingCost": {
            "value": "8.00",
            "currency": "USD"
        },
        "shipToLocations": [
            {"regionCode": "US"},
            {"regionCode": "JP"},
            {"regionCode": "GB"}
        ],
        "handlingTime": {
            "value": 2,
            "unit": "DAY"
        }
    }
    
    url = f"{EBAY_SANDBOX_API}/sell/fulfillment/v1/fulfillment_policy"
    result = make_request('POST', url, fulfillment_policy, use_user_token=True)
    
    if result['status'] in [200, 201]:
        policy_id = result['data'].get('fulfillmentPolicyId', '')
        print(f"✅ 物流政策创建成功：{policy_id}")
        policies['fulfillment'] = policy_id
    else:
        print(f"⚠️  物流政策创建失败：{result['status']}")
        policies['fulfillment'] = None
    
    # 2.3 退货政策
    print("\n2.3 创建退货政策...")
    return_policy = {
        "name": f"Test Return Policy {datetime.now().strftime('%Y%m%d%H%M%S')}",
        "description": "30 days return policy",
        "categoryType": "MARKETPLACE",
        "returnsAccepted": True,
        "refundMethod": "MONEY_BACK",
        "returnPeriod": {
            "value": "DAYS_30",
            "unit": "DAY"
        },
        "returnShippingCostPayer": "BUYER"
    }
    
    url = f"{EBAY_SANDBOX_API}/sell/fulfillment/v1/return_policy"
    result = make_request('POST', url, return_policy, use_user_token=True)
    
    if result['status'] in [200, 201]:
        policy_id = result['data'].get('returnPolicyId', '')
        print(f"✅ 退货政策创建成功：{policy_id}")
        policies['return'] = policy_id
    else:
        print(f"⚠️  退货政策创建失败：{result['status']}")
        policies['return'] = None
    
    return policies

# ============== 步骤 3: 创建库存商品 ==============
def step3_create_inventory_item(sku):
    """创建库存商品"""
    print("\n" + "=" * 60)
    print("步骤 3: 创建库存商品 (Inventory Item)")
    print("=" * 60)
    
    item_data = {
        "sku": sku,
        "product": {
            "title": TEST_PRODUCT['title'],
            "description": TEST_PRODUCT['description'],
            "imageUrls": [TEST_PRODUCT['image_url']],
            "condition": {
                "conditionDescriptor": "New",
                "conditionId": TEST_PRODUCT['condition']
            },
            "aspects": {
                "Brand": ["Hobonichi"],
                "Type": ["Planner"],
                "Features": ["Limited Edition"]
            }
        },
        "packageWeightAndSize": {
            "dimensions": {
                "width": "113",
                "length": "153",
                "height": "25",
                "unit": "MILLIMETER"
            },
            "weight": {
                "value": "330",
                "unit": "GRAM"
            }
        },
        "availability": {
            "shipToLocationAvailability": {
                "quantity": TEST_PRODUCT['quantity']
            }
        }
    }
    
    url = f"{EBAY_SANDBOX_API}/sell/inventory/v1/inventory_item/{sku}"
    
    print(f"创建商品 SKU: {sku}")
    print(f"标题：{TEST_PRODUCT['title'][:60]}...")
    
    result = make_request('PUT', url, item_data)
    
    if result['status'] in [200, 201, 204]:
        print("✅ 库存商品创建成功！")
        return True
    else:
        print(f"❌ 创建失败：{result['status']}")
        print(f"   {result['text'][:200]}")
        return False

# ============== 步骤 4: 创建销售报价 ==============
def step4_create_offer(sku, location_key, policies):
    """创建销售报价"""
    print("\n" + "=" * 60)
    print("步骤 4: 创建销售报价 (Create Offer)")
    print("=" * 60)
    
    offer_data = {
        "sku": sku,
        "marketplaceId": "EBAY_US",
        "categoryId": TEST_PRODUCT['category'],
        "pricingSummary": {
            "pricingStrategy": "FIXED_PRICING",
            "minimumPrice": {
                "value": str(TEST_PRODUCT['price']),
                "currency": "USD"
            }
        },
        "availability": {
            "shipToLocationAvailability": {
                "quantity": TEST_PRODUCT['quantity'],
                "shipToLocation": {
                    "regionCode": "US"
                }
            }
        },
        "fulfillmentStartEndDate": {
            "includeExcludeType": "INCLUDE",
            "dateRanges": []
        },
        "ebayAvailability": {
            "availabilityType": "IN_STOCK"
        }
    }
    
    # 添加政策（如果有）
    if policies.get('payment'):
        offer_data['paymentPolicyId'] = policies['payment']
    if policies.get('fulfillment'):
        offer_data['fulfillmentPolicyId'] = policies['fulfillment']
    if policies.get('return'):
        offer_data['returnPolicyId'] = policies['return']
    
    # 添加位置
    if location_key:
        offer_data['merchantLocationKey'] = location_key
    
    url = f"{EBAY_SANDBOX_API}/sell/inventory/v1/offer"
    
    print(f"创建报价 - SKU: {sku}")
    print(f"价格：${TEST_PRODUCT['price']}")
    print(f"分类：{TEST_PRODUCT['category']}")
    
    result = make_request('POST', url, offer_data)
    
    if result['status'] in [200, 201]:
        offer_id = result['data'].get('offerId', '')
        print(f"✅ 报价创建成功！")
        print(f"   Offer ID: {offer_id}")
        return offer_id
    else:
        print(f"❌ 创建失败：{result['status']}")
        print(f"   {result['text'][:300]}")
        return None

# ============== 步骤 5: 正式发布 ==============
def step5_publish_offer(offer_id):
    """发布报价"""
    print("\n" + "=" * 60)
    print("步骤 5: 正式发布 (Publish Offer)")
    print("=" * 60)
    
    url = f"{EBAY_SANDBOX_API}/sell/inventory/v1/offer/{offer_id}/publish"
    
    print(f"发布 Offer: {offer_id}")
    
    result = make_request('POST', url, None)
    
    if result['status'] in [200, 201, 204]:
        print("✅ Listing 发布成功！🎉")
        
        # 尝试获取 listing ID
        if result['data']:
            listing_id = result['data'].get('listingId', 'N/A')
            print(f"   Listing ID: {listing_id}")
            print(f"   查看链接：https://www.sandbox.ebay.com/itm/{listing_id}")
        
        return True
    else:
        print(f"❌ 发布失败：{result['status']}")
        print(f"   {result['text'][:300]}")
        return False

# ============== 主流程 ==============
def main():
    print("=" * 60)
    print("🛒 eBay 完整 Listing 发布流程")
    print("=" * 60)
    print(f"环境：沙盒 (Sandbox)")
    print(f"产品：{TEST_PRODUCT['title'][:50]}...")
    
    # 检查配置
    if not all([APP_ID, APP_SECRET, USER_TOKEN]):
        print("\n❌ 配置不完整，请检查 ebay_config.json")
        return
    
    # 步骤 1: 创建位置
    location_key = step1_create_location()
    if not location_key:
        print("\n⚠️  步骤 1 失败，但继续尝试...")
    
    # 步骤 2: 创建政策
    policies = step2_create_policies()
    
    # 步骤 3: 创建商品
    sku = TEST_PRODUCT['sku']
    if not step3_create_inventory_item(sku):
        print("\n❌ 步骤 3 失败，停止")
        return
    
    # 步骤 4: 创建报价
    offer_id = step4_create_offer(sku, location_key, policies)
    if not offer_id:
        print("\n❌ 步骤 4 失败，停止")
        return
    
    # 步骤 5: 发布
    if step5_publish_offer(offer_id):
        print("\n" + "=" * 60)
        print("🎉 恭喜！完整流程成功完成！")
        print("=" * 60)
        print(f"""
✅ 所有步骤已完成！

你的 Listing 信息：
- SKU: {sku}
- Offer ID: {offer_id}
- 仓库：{location_key or '默认'}
- 政策：付款{'✓' if policies.get('payment') else '✗'}, 物流{'✓' if policies.get('fulfillment') else '✗'}, 退货{'✓' if policies.get('return') else '✗'}

下一步：
1. 访问沙盒 eBay 查看 Listing
2. 测试购买流程
3. 明天学习每个步骤的细节
""")
    else:
        print("\n⚠️  发布失败，但前面步骤都成功了！")
        print("明天可以调试这一步。")

if __name__ == "__main__":
    main()
