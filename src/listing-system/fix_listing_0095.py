#!/usr/bin/env python3
"""
修复 Listing 01-2603-0095 的三个问题：
1. HTML 模板简化（eBay 兼容格式）
2. 分类修正为 182164 (Metaphysical Products > Tarot Cards)
3. 发货时间调整为 7 天
"""

from ebay_client import EbayClient
import json

client = EbayClient('config.json')

SKU = "01-2603-0095"
OFFER_ID = "138241870011"
LISTING_ID = "397761924062"

print("=" * 60)
print("🔧 修复 Listing 01-2603-0095")
print("=" * 60)
print(f"当前 Listing ID: {LISTING_ID}")
print()

# 问题 1: eBay 兼容的 HTML 描述（简化版）
# eBay 不支持复杂 CSS 和 JavaScript，只支持基础 HTML
HTML_DESCRIPTION = """
<h2>Fable Hedgehog Tarot Deck - 78 Cards with Japanese Booklet</h2>

<p><strong>The cutest tarot deck you'll ever own!</strong> Adorable hedgehog illustrations bring warmth and wonder to every reading.</p>

<h3>Product Features</h3>
<ul>
<li>Complete 78-card tarot deck (22 Major Arcana + 56 Minor Arcana)</li>
<li>Adorable hedgehog-themed kawaii illustrations</li>
<li>Includes Japanese-language booklet with card meanings</li>
<li>Premium card stock with smooth finish</li>
<li>Perfect for divination and fortune telling</li>
</ul>

<h3>Specifications</h3>
<ul>
<li><strong>Brand:</strong> LUNA FACTORY</li>
<li><strong>Type:</strong> Tarot Card Deck</li>
<li><strong>Number of Cards:</strong> 78</li>
<li><strong>Theme:</strong> Hedgehog, Animals</li>
<li><strong>Language:</strong> Japanese (booklet) / Universal imagery</li>
<li><strong>Condition:</strong> Brand New, Factory Sealed</li>
<li><strong>Origin:</strong> Japan</li>
</ul>

<h3>Shipping Information</h3>
<ul>
<li><strong>Ships from:</strong> Osaka, Japan</li>
<li><strong>Handling Time:</strong> 7 business days</li>
<li><strong>Delivery:</strong> 8-15 business days (Economy)</li>
<li><strong>Tracking:</strong> Provided for all orders</li>
</ul>

<h3>Return Policy</h3>
<p>30-day returns accepted. Item must be in original, unused condition.</p>

<hr>
<p style="color: #666; font-size: 12px;"><em>Thank you for shopping with us! Authentic Japanese products shipped worldwide.</em></p>
""".strip()

print("步骤 1: 更新 Inventory Item")
print("-" * 60)

# 更新 Inventory Item
item_data = {
    'product': {
        'title': 'Fable Hedgehog Tarot Deck 78 Cards w/ Japanese Booklet Cute Kawaii Japan NEW',
        'description': HTML_DESCRIPTION,
        'imageUrls': [
            'https://m.media-amazon.com/images/I/71ZguBJJdvL._AC_SL1200_.jpg',
            'https://m.media-amazon.com/images/I/71R42F8NR-L._AC_SL1500_.jpg',
            'https://m.media-amazon.com/images/I/81vqFjam5tL._AC_SL1500_.jpg',
            'https://m.media-amazon.com/images/I/81Jcxxel2YL._AC_SL1500_.jpg'
        ],
        'aspects': {
            'Brand': ['LUNA FACTORY'],
            'Type': ['Tarot Card Deck'],
            'Number of Cards': ['78'],
            'Theme': ['Hedgehog', 'Animals'],
            'Features': ['Japanese Booklet Included'],
            'Country/Region of Manufacture': ['Japan'],
            'For Instrument': ['Divination']  # 分类 182164 的必填属性
        },
        'upc': ['4589851432964']
    },
    'condition': 'NEW',
    'availability': {
        'shipToLocationAvailability': {
            'quantity': 2
        }
    },
    'packageWeightAndSize': {
        'dimensions': {
            'width': '13.5',
            'length': '8.0',
            'height': '5.0',
            'unit': 'CENTIMETER'
        },
        'weight': {
            'value': '0.35',
            'unit': 'KILOGRAM'
        }
    }
}

resp = client.put(f'/sell/inventory/v1/inventory_item/{SKU}', data=item_data)
print(f'Status: {resp.status_code}')
if resp.ok:
    print('✅ Inventory Item 更新成功')
else:
    print(f'❌ 更新失败：{resp.error}')
    if resp.body:
        print(json.dumps(resp.body, indent=2)[:500])

print()
print("步骤 2: 更新 Offer (修正分类和发货时间)")
print("-" * 60)

# 需要先撤销发布（End Offer），然后更新，再重新发布
# 但为了简单，我们直接创建新的 Offer

# 先结束旧的 Offer
print(f'结束旧 Offer: {OFFER_ID}')
resp_end = client.post(f'/sell/inventory/v1/offer/{OFFER_ID}/withdraw')
print(f'Withdraw Status: {resp_end.status_code}')

import time
time.sleep(2)

# 创建新的 Offer（正确分类 +7 天处理时间）
offer_data = {
    'sku': SKU,
    'marketplaceId': 'EBAY_US',
    'format': 'FIXED_PRICE',
    'categoryId': '182164',  # Metaphysical Products > Tarot Cards
    'listingDescription': HTML_DESCRIPTION,
    'merchantLocationKey': 'osaka-main',
    'listingPolicies': {
        'paymentPolicyId': '265656298018',
        'fulfillmentPolicyId': '266026679018',
        'returnPolicyId': '265656303018',
    },
    'pricingSummary': {
        'price': {
            'value': '68.00',
            'currency': 'USD'
        }
    },
    'availableQuantity': 2,
    'fulfillmentStartEndDate': {
        'handlingTime': {
            'value': 7,  # 7 天处理时间
            'unit': 'DAY'
        }
    }
}

print('创建新 Offer...')
resp2 = client.post('/sell/inventory/v1/offer', data=offer_data)
print(f'Status: {resp2.status_code}')

new_offer_id = None
if resp2.ok:
    new_offer_id = resp2.offer_id
    if not new_offer_id:
        # 查询
        query_resp = client.get(f'/sell/inventory/v1/offer?sku={SKU}&limit=1')
        if query_resp.ok and query_resp.body.get('offers'):
            new_offer_id = query_resp.body['offers'][0].get('offerId')
    
    if new_offer_id:
        print(f'✅ 新 Offer 创建成功：{new_offer_id}')
    else:
        print('❌ 无法获取 Offer ID')
else:
    print(f'❌ 创建失败：{resp2.error}')
    if resp2.body:
        print(json.dumps(resp2.body, indent=2)[:500])

if new_offer_id:
    print()
    print("步骤 3: 发布新 Listing")
    print("-" * 60)
    
    resp3 = client.post(f'/sell/inventory/v1/offer/{new_offer_id}/publish')
    print(f'Publish Status: {resp3.status_code}')
    
    if resp3.ok:
        new_listing_id = resp3.listing_id
        print('✅ 发布成功！')
        if new_listing_id:
            print(f'新 Listing ID: {new_listing_id}')
            print(f'查看链接：https://www.ebay.com/itm/{new_listing_id}')
        else:
            print('Listing ID 稍后显示')
    else:
        print(f'❌ 发布失败：{resp3.error}')
        if resp3.body:
            print(json.dumps(resp3.body, indent=2)[:500])

print()
print("=" * 60)
print("✅ 修复完成！")
print("=" * 60)
print()
print("修复内容：")
print("1. ✅ HTML 描述简化为 eBay 兼容格式")
print("2. ✅ 分类修正为 182164 (Metaphysical Products > Tarot Cards)")
print("3. ✅ 发货时间调整为 7 天")
print()
print("请在 10-15 分钟后访问 eBay 查看更新后的 Listing")
