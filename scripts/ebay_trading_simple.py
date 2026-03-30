#!/usr/bin/env python3
"""
eBay Trading API 发布 Listing - 简化版
使用最基本的字段，避免业务政策问题
"""

import requests
import json
from datetime import datetime

with open('ebay_config.json') as f:
    config = json.load(f)

USER_TOKEN = config.get('OAUTH_TOKEN', '')
APP_ID = config.get('EBAY_APP_ID', '')

# Trading API 端点
TRADING_API = "https://api.sandbox.ebay.com/ws/api.dll"

# 简化的 XML 请求模板
XML_TEMPLATE = """<?xml version="1.0" encoding="utf-8"?>
<AddItemRequest xmlns="urn:ebay:apis:eBLBaseComponents">
  <RequesterCredentials>
    <eBayAuthToken>{token}</eBayAuthToken>
  </RequesterCredentials>
  <ErrorLanguage>en_US</ErrorLanguage>
  <WarningLevel>High</WarningLevel>
  <Item>
    <Title>{title}</Title>
    <Description><![CDATA[{description}]]></Description>
    <PrimaryCategory>
      <CategoryID>11450</CategoryID>
    </PrimaryCategory>
    <StartPrice>{price}</StartPrice>
    <CategoryMappingAllowed>true</CategoryMappingAllowed>
    <Country>US</Country>
    <Currency>USD</Currency>
    <ConditionID>1000</ConditionID>
    <ListingDuration>Days_7</ListingDuration>
    <ListingType>FixedPriceItem</ListingType>
    <PaymentMethods>VisaMC</PaymentMethods>
    <PostalCode>10001</PostalCode>
    <Quantity>1</Quantity>
    <ReturnPolicy>
      <ReturnsAcceptedOption>ReturnsNotAccepted</ReturnsAcceptedOption>
    </ReturnPolicy>
    <Site>US</Site>
    <SKU>{sku}</SKU>
  </Item>
</AddItemRequest>
"""

def add_item(sku, title, price):
    """使用 Trading API 发布 Listing"""
    
    xml_payload = XML_TEMPLATE.format(
        token=USER_TOKEN,
        title=title,
        description=title,
        sku=sku,
        price=price
    )
    
    headers = {
        "X-EBAY-API-COMPATIBILITY-LEVEL": "1113",
        "X-EBAY-API-CALL-NAME": "AddItem",
        "X-EBAY-API-SITEID": "0",
        "X-EBAY-API-APP-NAME": config.get('EBAY_APP_ID', ''),
        "X-EBAY-API-DEV-NAME": config.get('EBAY_DEV_ID', ''),
        "X-EBAY-API-CERT-NAME": config.get('EBAY_APP_SECRET', ''),
        "Content-Type": "text/xml"
    }
    
    print(f"发送 AddItem 请求...")
    print(f"SKU: {sku}")
    print(f"标题：{title}")
    print(f"价格：${price}")
    
    resp = requests.post(TRADING_API, data=xml_payload, headers=headers)
    
    print(f"\n响应状态码：{resp.status_code}")
    
    # 解析 XML 响应
    response_text = resp.text
    print(f"\n原始响应：")
    print(response_text[:1500])
    
    # 检查是否成功
    if "<Ack>Success</Ack>" in response_text or "<Ack>Warning</Ack>" in response_text:
        # 提取 ItemID
        import re
        item_id_match = re.search(r'<ItemID>(.*?)</ItemID>', response_text)
        if item_id_match:
            item_id = item_id_match.group(1)
            print(f"\n✅ Listing 发布成功！")
            print(f"Item ID: {item_id}")
            print(f"查看 Listing: https://www.sandbox.ebay.com/itm/{item_id}")
            return True, item_id
    
    print(f"\n❌ 发布失败")
    return False, None

# 主程序
if __name__ == "__main__":
    print("=" * 60)
    print("🛒 eBay Trading API 发布测试 - 简化版")
    print("=" * 60)
    
    # 生成 SKU
    timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
    sku = f"TRADING{timestamp}"
    
    # 发布测试产品
    success, item_id = add_item(
        sku=sku,
        title="Test Product - Hobonichi Techo",
        price="10.00"
    )
    
    print("\n" + "=" * 60)
    if success:
        print("🎉 完成！")
    else:
        print("⚠️  请检查错误信息")
    print("=" * 60)
