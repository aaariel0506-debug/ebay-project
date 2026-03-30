#!/usr/bin/env python3
"""
测试发布：Fable Hedgehog Tarot Deck
SKU: 01-2603-0095
"""

import sys
import json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from ebay_client import EbayClient

# 初始化客户端
client = EbayClient("config.json")

print("=" * 60)
print("🔮 测试发布：Fable Hedgehog Tarot Deck")
print("=" * 60)
print(f"环境：{client.config.get('environment', 'unknown')}")
print(f"API: {client.api_base}")
print(f"SKU: 01-2603-0095")
print("=" * 60)

# 商品数据
SKU = "01-2603-0095"
item_data = {
    "sku": SKU,
    "product": {
        "title": "Fable Hedgehog Tarot Deck 78 Cards w/ Japanese Booklet Cute Kawaii Japan NEW",
        "upc": ["4589851432964"],
        "description": """
<h2>Fable Hedgehog Tarot Deck &ndash; 78 Cards with Japanese Booklet</h2>
<p>The cutest tarot deck you&rsquo;ll ever own &ndash; adorable hedgehog illustrations bring warmth and wonder to every reading.</p>
<p>Introducing the <strong>Fable Hedgehog Tarot</strong> &ndash; a beautifully illustrated 78-card tarot deck featuring charming hedgehog characters in whimsical, storybook-style artwork.</p>
<p>This authentic Japanese edition includes a <strong>Japanese-language booklet</strong> with card meanings and spread guides.</p>
""",
        "imageUrls": [
            "https://m.media-amazon.com/images/I/71ZguBJJdvL._AC_SL1200_.jpg",
            "https://m.media-amazon.com/images/I/71R42F8NR-L._AC_SL1500_.jpg",
            "https://m.media-amazon.com/images/I/81vqFjam5tL._AC_SL1500_.jpg",
            "https://m.media-amazon.com/images/I/81Jcxxel2YL._AC_SL1500_.jpg"
        ],
        "aspects": {
            "Brand": ["LUNA FACTORY"],
            "Type": ["Tarot Card Deck"],
            "Theme": ["Hedgehog", "Animals"],
            "Number of Cards": ["78"],
            "Features": ["Japanese Booklet Included"],
            "Country/Region of Manufacture": ["Japan"]
        }
    },
    "condition": "NEW",
    "availability": {
        "shipToLocationAvailability": {
            "quantity": 2
        }
    },
    "packageWeightAndSize": {
        "dimensions": {
            "width": "13.5",
            "length": "8.0",
            "height": "5.0",
            "unit": "CENTIMETER"
        },
        "weight": {
            "value": "0.35",
            "unit": "KILOGRAM"
        }
    }
}

offer_data = {
    "sku": SKU,
    "marketplaceId": "EBAY_US",
    "format": "FIXED_PRICE",
    "categoryId": "182164",  # Metaphysical Products > Tarot Cards
    "listingDescription": item_data["product"]["description"],
    "merchantLocationKey": client.merchant_location_key,
    "listingPolicies": {
        "paymentPolicyId": client.payment_policy_id,
        "fulfillmentPolicyId": client.fulfillment_policy_id,
        "returnPolicyId": client.return_policy_id,
    },
    "pricingSummary": {
        "price": {
            "value": "68.00",
            "currency": "USD"
        }
    },
    "availableQuantity": 2,
    "fulfillmentStartEndDate": {
        "handlingTime": {
            "value": 3,
            "unit": "DAY"
        }
    }
}

# 步骤 1: 创建 Inventory Item
print("\n" + "=" * 60)
print("步骤 1: 创建 Inventory Item")
print("=" * 60)

resp1 = client.put(f"/sell/inventory/v1/inventory_item/{SKU}", data=item_data)

if resp1.ok:
    print(f"✅ Inventory Item 创建成功！(HTTP {resp1.status_code})")
else:
    print(f"❌ 失败：{resp1.status_code}")
    print(f"错误：{resp1.error}")
    if resp1.body:
        print(f"详情：{json.dumps(resp1.body, indent=2)[:500]}")
    sys.exit(1)

# 步骤 2: 创建 Offer
print("\n" + "=" * 60)
print("步骤 2: 创建 Offer")
print("=" * 60)

resp2 = client.post("/sell/inventory/v1/offer", data=offer_data)

if resp2.ok:
    offer_id = resp2.offer_id
    if not offer_id:
        # 查询
        query_resp = client.get(f"/sell/inventory/v1/offer?sku={SKU}&limit=1")
        if query_resp.ok and query_resp.body.get("offers"):
            offer_id = query_resp.body["offers"][0].get("offerId", "")
    
    if offer_id:
        print(f"✅ Offer 创建成功！")
        print(f"   Offer ID: {offer_id}")
    else:
        print("❌ 无法获取 Offer ID")
        sys.exit(1)
else:
    print(f"❌ 失败：{resp2.status_code}")
    print(f"错误：{resp2.error}")
    if resp2.body:
        print(f"详情：{json.dumps(resp2.body, indent=2)[:500]}")
    sys.exit(1)

# 步骤 3: 发布（草稿模式，不实际发布）
print("\n" + "=" * 60)
print("步骤 3: 创建草稿（UNPUBLISHED）")
print("=" * 60)

print(f"⚠️  注意：当前配置 require_review=true，创建为草稿状态")
print(f"   请在 eBay Seller Hub → Drafts 中检查并手动发布")
print(f"   Drafts 链接：https://www.ebay.com/sh/lst/drafts")

print("\n" + "=" * 60)
print("✅ 测试完成！草稿已创建")
print("=" * 60)
print(f"""
商品信息：
- SKU: {SKU}
- Offer ID: {offer_id}
- 标题：{item_data['product']['title'][:60]}...
- 售价：$68.00
- 运费：$15.99
- 总价：$83.99
- 库存：2

下一步：
1. 访问 eBay Seller Hub → Drafts
2. 找到 SKU {SKU} 的草稿
3. 检查所有信息
4. 手动点击发布
""")
print("=" * 60)
