#!/usr/bin/env python3
"""
eBay Listing 创建脚本 - 生产环境
使用 ebay_client.py 统一客户端
"""

import sys
import time
from pathlib import Path
from ebay_client import EbayClient

def create_listing(client, sku, title, price, quantity=1):
    """
    创建 Listing 完整流程
    
    Args:
        client: EbayClient 实例
        sku: 商品 SKU（字母数字）
        title: 商品标题
        price: 价格（美元）
        quantity: 库存数量
    
    Returns:
        dict: 创建结果，包含 listing_id
    """
    result = {'sku': sku, 'success': False}
    
    # ─── 步骤 1: 创建 Inventory Item ─────────────────────
    print(f"\n{'='*60}")
    print(f"步骤 1: 创建 Inventory Item (SKU: {sku})")
    print(f"{'='*60}")
    
    item_data = {
        "sku": sku,
        "product": {
            "title": title,
            "aspects": {}
        }
    }
    
    resp = client.put(f'/sell/inventory/v1/inventory_item/{sku}', data=item_data)
    print(f"状态码：{resp.status_code}")
    
    if not resp.ok and resp.status_code not in [200, 201, 204]:
        print(f"❌ 失败：{resp.error[:200]}")
        result['error_step1'] = resp.error
        return result
    
    print("✅ Inventory Item 创建成功")
    result['item_created'] = True
    
    # 等待系统同步
    time.sleep(2)
    
    # ─── 步骤 2: 创建 Offer ──────────────────────────────
    print(f"\n{'='*60}")
    print("步骤 2: 创建 Offer")
    print(f"{'='*60}")
    
    offer_data = {
        "sku": sku,
        "marketplaceId": client.marketplace_id,
        "categoryId": "11450",  # Paper & Page Additions
        "format": client.config.get('listing_defaults', {}).get('format', 'FIXED_PRICE'),
        "pricingSummary": {
            "minimumPrice": {
                "value": str(price),
                "currency": client.currency
            }
        },
        "availability": {
            "shipToLocationAvailability": {
                "quantity": quantity
            }
        }
    }
    
    # 添加业务策略
    policies = client.config.get('business_policies', {})
    if policies.get('payment_policy_id'):
        offer_data["paymentPolicyId"] = policies['payment_policy_id']
    if policies.get('fulfillment_policy_id'):
        offer_data["fulfillmentPolicyId"] = policies['fulfillment_policy_id']
    if policies.get('return_policy_id'):
        offer_data["returnPolicyId"] = policies['return_policy_id']
    
    # 添加 Merchant Location（如果配置了）
    merchant_key = client.config.get('merchant_location_key', '')
    if merchant_key:
        offer_data["merchantLocationKey"] = merchant_key
    
    resp = client.post('/sell/inventory/v1/offer', data=offer_data)
    print(f"状态码：{resp.status_code}")
    
    if not resp.ok and resp.status_code not in [200, 201]:
        print(f"❌ 失败：{resp.error[:300]}")
        result['error_step2'] = resp.error
        return result
    
    print("✅ Offer 创建成功")
    
    # 获取 Offer ID
    offer_id = resp.offer_id
    if not offer_id:
        # 查询获取
        time.sleep(2)
        query_resp = client.get(f'/sell/inventory/v1/offer?sku={sku}')
        if query_resp.ok and query_resp.body:
            offers = query_resp.body.get('offers', [])
            if offers:
                offer_id = offers[0].get('offerId')
    
    if not offer_id:
        print("⚠️ 无法获取 Offer ID")
        result['error_step2'] = 'No offer_id'
        return result
    
    print(f"Offer ID: {offer_id}")
    result['offer_id'] = offer_id
    
    # ─── 步骤 3: 发布 Listing（可选，根据配置）────────────────
    auto_publish = client.config.get('listing_defaults', {}).get('auto_publish', False)
    require_review = client.config.get('workflow', {}).get('require_review', True)
    
    if auto_publish and not require_review:
        print(f"\n{'='*60}")
        print("步骤 3: 发布 Listing")
        print(f"{'='*60}")
        
        pub_resp = client.post(f'/sell/inventory/v1/offer/{offer_id}/publish')
        print(f"状态码：{pub_resp.status_code}")
        
        if pub_resp.ok or pub_resp.status_code in [200, 201, 204]:
            print("\n🎉 成功！Listing 发布成功！")
            listing_id = pub_resp.listing_id
            if listing_id:
                print(f"Listing ID: {listing_id}")
                print(f"查看：https://www.ebay.com/itm/{listing_id}")
                result['listing_id'] = listing_id
            result['success'] = True
        else:
            print(f"❌ 发布失败：{pub_resp.error[:300]}")
            result['error_step3'] = pub_resp.error
    else:
        print(f"\n{'='*60}")
        print("步骤 3: 跳过发布（进入预审核）")
        print(f"{'='*60}")
        print(f"✅ Listing 已创建为草稿（UNPUBLISHED）")
        print(f"Offer ID: {offer_id}")
        print(f"\n📋 下一步操作：")
        print(f"  1. 访问预审核页面编辑商品信息：")
        print(f"     http://127.0.0.1:8080")
        print(f"  2. 检查并补充必要字段（如 Brand）")
        print(f"  3. 点击「保存并发布」上架")
        print(f"\n⚠️  注意：直接调用 API 发布也会被阻止，必须通过预审核页面")
        result['success'] = True
        result['status'] = 'UNPUBLISHED'
    
    return result


def main():
    """主函数"""
    config_path = Path(__file__).parent / "config.json"
    
    print("=" * 60)
    print("🛒 eBay Listing 创建工具 - 生产环境")
    print("=" * 60)
    
    # 初始化客户端
    try:
        client = EbayClient(config_path)
    except Exception as e:
        print(f"❌ 初始化失败：{e}")
        sys.exit(1)
    
    print(f"环境：{client.config.get('environment')}")
    print(f"API: {client.api_base}")
    
    # 测试连接
    print("\n测试 API 连接...")
    if not client.test_connection():
        print("❌ API 连接失败，请检查 Token")
        sys.exit(1)
    print("✅ API 连接正常")
    
    # 示例 Listing
    print("\n" + "=" * 60)
    print("创建示例 Listing")
    print("=" * 60)
    
    import random
    sku = f"TEST{random.randint(10000, 99999)}"
    title = "Hobonichi 5-Year Techo Gift Edition 2026-2030"
    price = 89.99
    quantity = 5
    
    print(f"SKU: {sku}")
    print(f"标题：{title}")
    print(f"价格：${price}")
    print(f"数量：{quantity}")
    
    # 创建 Listing
    result = create_listing(client, sku, title, price, quantity)
    
    # 输出结果
    print("\n" + "=" * 60)
    print("最终结果")
    print("=" * 60)
    
    if result.get('success'):
        print("✅ Listing 创建成功！")
        if result.get('listing_id'):
            print(f"Listing ID: {result['listing_id']}")
            print(f"URL: https://www.ebay.com/itm/{result['listing_id']}")
    else:
        print("❌ Listing 创建失败")
        for key, value in result.items():
            if key.startswith('error'):
                print(f"  {key}: {value[:200]}")
    
    return result


if __name__ == "__main__":
    main()
