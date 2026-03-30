#!/usr/bin/env python3
"""
eBay Trading API 发布 Listing
使用 AddItem 调用一步完成发布
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

# XML 请求模板
XML_TEMPLATE = """<?xml version="1.0" encoding="utf-8"?>
<AddItemRequest xmlns="urn:ebay:apis:eBLBaseComponents">
  <RequesterCredentials>
    <eBayAuthToken>{token}</eBayAuthToken>
  </RequesterCredentials>
  <ErrorLanguage>en_US</ErrorLanguage>
  <WarningLevel>High</WarningLevel>
  <Item>
    <Title>{title}</Title>
    <Description>{description}</Description>
    <PrimaryCategory>
      <CategoryID>11450</CategoryID>
    </PrimaryCategory>
    <StartPrice>{price}</StartPrice>
    <CategoryMappingAllowed>true</CategoryMappingAllowed>
    <Country>US</Country>
    <Currency>USD</Currency>
    <ConditionID>1000</ConditionID>
    <ListingDuration>GTC</ListingDuration>
    <ListingType>FixedPriceItem</ListingType>
    <PaymentMethods>PayPal</PaymentMethods>
    <PayPalEmailAddress>{paypal_email}</PayPalEmailAddress>
    <PictureDetails>
      <PictureURL>{picture_url}</PictureURL>
    </PictureDetails>
    <PostalCode>10001</PostalCode>
    <Quantity>{quantity}</Quantity>
    <ReturnPolicy>
      <ReturnsAcceptedOption>ReturnsAccepted</ReturnsAcceptedOption>
      <RefundOption>MoneyBack</RefundOption>
      <ReturnsWithinOption>Days_30</ReturnsWithinOption>
      <ShippingCostPaidByOption>Buyer</ShippingCostPaidByOption>
    </ReturnPolicy>
    <ShippingDetails>
      <ShippingType>Flat</ShippingType>
      <ShippingServiceOptions>
        <ShippingServicePriority>1</ShippingServicePriority>
        <ShippingService>USPSFirstClass</ShippingService>
        <ShippingServiceCost>3.99</ShippingServiceCost>
      </ShippingServiceOptions>
    </ShippingDetails>
    <Site>US</Site>
    <SKU>{sku}</SKU>
  </Item>
</AddItemRequest>
"""

def add_item(sku, title, price, buyitnow, quantity, picture_url=""):
    """使用 Trading API 发布 Listing"""
    
    xml_payload = XML_TEMPLATE.format(
        token=USER_TOKEN,
        title=title,
        description=title,
        sku=sku,
        price=price,
        buyitnow=buyitnow,
        quantity=quantity,
        picture_url=picture_url,
        paypal_email="test@example.com"  # 沙盒环境可用测试邮箱
    )
    
    headers = {
        "X-EBAY-API-COMPATIBILITY-LEVEL": "1113",
        "X-EBAY-API-CALL-NAME": "AddItem",
        "X-EBAY-API-SITEID": "0",
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
    print(response_text[:1000])
    
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
    print("🛒 eBay Trading API 发布测试")
    print("=" * 60)
    
    # 生成 SKU
    timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
    sku = f"TRADING{timestamp}"
    
    # 发布测试产品
    success, item_id = add_item(
        sku=sku,
        title="Hobonichi 5-Year Techo Gift Edition 2026-2030",
        price="189",
        buyitnow="189",
        quantity="1",
        picture_url="https://pics.ebaystatic.com/pict/225379669339-0-0.jpg"
    )
    
    print("\n" + "=" * 60)
    if success:
        print("🎉 完成！")
    else:
        print("⚠️  请检查错误信息")
    print("=" * 60)
