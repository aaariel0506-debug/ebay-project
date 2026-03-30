#!/usr/bin/env python3
"""
eBay 传统发布 API - 使用 Trading API 的 AddFixedPriceItem
作为 Inventory API 的备用方案

优势：
- 直接创建草稿，同步更快
- 字段更完整，兼容性更好
- eBay 后台立即显示
"""

import sys
import json
import base64
import requests
from pathlib import Path
from datetime import datetime

# 加载配置
config_path = Path(__file__).parent / 'config.json'
with open(config_path, 'r') as f:
    config = json.load(f)

# eBay API 配置
EBAY_API = "https://api.ebay.com"  # 生产环境
APP_ID = config['production']['app_id']
APP_SECRET = config['production']['app_secret']
DEV_ID = config['production']['dev_id']

# 使用 ebay_client 获取有效的 User Token
sys.path.insert(0, str(Path(__file__).parent))
from ebay_client import EbayClient
client = EbayClient('config.json')
USER_TOKEN = client.get_user_token()

if not USER_TOKEN:
    print("❌ 无法获取有效的 User Token，请先运行 oauth 授权")
    sys.exit(1)

# 商品数据
SKU = "01-2603-0095"
ITEM_DATA = {
    "Title": "Fable Hedgehog Tarot Deck 78 Cards w/ Japanese Booklet Cute Kawaii Japan NEW",
    "Subtitle": "Adorable Hedgehog Illustrations - Authentic Japanese Tarot Cards",
    "Description": """
<!DOCTYPE html>
<html>
<head>
<style>
body { font-family: Arial, sans-serif; line-height: 1.6; color: #333; }
h2 { color: #2c5530; border-bottom: 2px solid #2c5530; padding-bottom: 10px; }
.highlight { background: #f5f9f5; padding: 15px; border-left: 4px solid #2c5530; margin: 15px 0; }
.features { background: #fafafa; padding: 15px; border-radius: 5px; }
.features ul { margin: 10px 0; padding-left: 20px; }
.features li { margin: 8px 0; }
.shipping { background: #fff8e1; padding: 15px; border: 1px solid #ffe082; margin-top: 20px; }
</style>
</head>
<body>
<h2>Fable Hedgehog Tarot Deck &ndash; 78 Cards with Japanese Booklet</h2>

<div class="highlight">
<p style="margin: 0; font-size: 15px; color: #856404; font-weight: 700;">
🌟 Premium Service | 100% Authentic | Direct from Japan
</p>
</div>

<p style="font-size: 18px; margin-bottom: 20px; color: #2F3E46; font-weight: bold;">
The cutest tarot deck you'll ever own &ndash; adorable hedgehog illustrations bring warmth and wonder to every reading.
</p>

<div class="features">
<h3>Key Features</h3>
<ul>
<li>Complete 78-card deck (22 Major Arcana + 56 Minor Arcana)</li>
<li>Adorable hedgehog-themed kawaii illustrations throughout</li>
<li>Includes Japanese-language interpretation booklet</li>
<li>Premium card stock with smooth, durable finish</li>
</ul>
</div>

<h3>Product Specifications</h3>
<ul>
<li><strong>Brand:</strong> LUNA FACTORY</li>
<li><strong>Type:</strong> Tarot Card Deck</li>
<li><strong>Number of Cards:</strong> 78</li>
<li><strong>Theme:</strong> Hedgehog, Animals</li>
<li><strong>Language:</strong> Japanese (booklet) / Universal imagery</li>
<li><strong>Condition:</strong> Brand New, Factory Sealed</li>
<li><strong>Origin:</strong> Japan</li>
</ul>

<div class="shipping">
<h3>Shipping Information</h3>
<p><strong>Ships from:</strong> Osaka, Japan</p>
<p><strong>Handling time:</strong> 3 business days</p>
<p><strong>Delivery time:</strong> 8-15 business days (Economy) / 2-5 business days (Expedited)</p>
<p style="color: #2c5530;"><strong>🎉 Free shipping on orders over $50!</strong></p>
</div>

<p style="margin-top: 30px; color: #666; font-size: 12px;">
<em>Thank you for shopping with us! If you have any questions, please feel free to contact us.</em>
</p>
</body>
</html>
""",
    "PrimaryCategory": {
        "CategoryID": "182164"  # Metaphysical Products > Tarot Cards
    },
    "CategoryMappingAllowed": True,
    "ConditionID": 1000,  # New
    "ListingType": "FixedPrice",
    "ListingDuration": "GTC",  # Good 'Til Cancelled
    "StartPrice": 68.00,
    "BuyItNowPrice": 68.00,
    "Quantity": 2,
    "SKU": SKU,
    "UPC": "4589851432964",
    "PictureDetails": {
        "GalleryType": "Gallery",
        "PictureURL": [
            "https://m.media-amazon.com/images/I/71ZguBJJdvL._AC_SL1200_.jpg",
            "https://m.media-amazon.com/images/I/71R42F8NR-L._AC_SL1500_.jpg",
            "https://m.media-amazon.com/images/I/81vqFjam5tL._AC_SL1500_.jpg",
            "https://m.media-amazon.com/images/I/81Jcxxel2YL._AC_SL1500_.jpg"
        ]
    },
    "ItemSpecifics": {
        "NameValueList": [
            {"Name": "Brand", "Value": ["LUNA FACTORY"]},
            {"Name": "Type", "Value": ["Tarot Card Deck"]},
            {"Name": "Number of Cards", "Value": ["78"]},
            {"Name": "Theme", "Value": ["Hedgehog", "Animals"]},
            {"Name": "Features", "Value": ["Japanese Booklet Included"]},
            {"Name": "Country/Region of Manufacture", "Value": ["Japan"]},
            {"Name": "UPC", "Value": ["4589851432964"]}
        ]
    },
    "Location": "Osaka",
    "Country": "JP",
    "Currency": "USD",
    "PaymentMethods": ["PayPal", "CreditCard"],
    "PayPalEmailAddress": config.get('paypal_email', ''),  # 可选
    "ShippingDetails": {
        "ShippingType": "Flat",
        "ShippingServiceOptions": [
            {
                "ShippingServicePriority": 1,
                "ShippingService": "USPSPriority",
                "ShippingServiceCost": 15.99,
                "ShippingServiceAdditionalCost": 0.0,
                "FreeShipping": False,
                "ExpeditedService": False
            }
        ],
        "InternationalShippingServiceOption": [
            {
                "ShippingServicePriority": 1,
                "ShippingService": "USPSPriorityMailInternational",
                "ShippingServiceCost": 25.99,
                "ShipToLocation": ["Worldwide"]
            }
        ],
        "SalesTax": {
            "SalesTaxPercent": 0.0,
            "TaxIncludedInShippingDetails": False
        }
    },
    "ReturnPolicy": {
        "ReturnsAcceptedOption": "ReturnsAccepted",
        "RefundOption": "MoneyBack",
        "ReturnsWithinOption": "Days30",
        "ShippingCostPaidByOption": "Buyer",
        "Description": "30 days return policy. Item must be in original, unused condition."
    },
    "Site": "US",
    "ListingSite": "US"
}


def get_trading_api_endpoint():
    """获取 Trading API 端点"""
    return "https://api.ebay.com/ws/api.dll"


def build_add_fixed_price_item_request(item_data, create_draft=False):
    """
    构建 AddFixedPriceItem 请求 XML
    
    Args:
        item_data: 商品数据字典
        create_draft: True=创建草稿，False=直接发布
    
    Returns:
        XML 字符串
    """
    # 构建 Item Specifics XML
    item_specifics_xml = ""
    if "ItemSpecifics" in item_data:
        specifics = item_data["ItemSpecifics"]
        item_specifics_xml = "<ItemSpecifics>"
        for nv in specifics["NameValueList"]:
            item_specifics_xml += f"<NameValueList><Name>{nv['Name']}</Name>"
            for val in nv["Value"]:
                item_specifics_xml += f"<Value>{val}</Value>"
            item_specifics_xml += "</NameValueList>"
        item_specifics_xml += "</ItemSpecifics>"
    
    # 构建图片 XML
    pictures_xml = ""
    if "PictureDetails" in item_data:
        pics = item_data["PictureDetails"]
        pictures_xml = "<PictureDetails>"
        if "GalleryType" in pics:
            pictures_xml += f"<GalleryType>{pics['GalleryType']}</GalleryType>"
        if "PictureURL" in pics:
            for url in pics["PictureURL"]:
                pictures_xml += f"<PictureURL>{url}</PictureURL>"
        pictures_xml += "</PictureDetails>"
    
    # 构建运费 XML
    shipping_xml = ""
    if "ShippingDetails" in item_data:
        ship = item_data["ShippingDetails"]
        shipping_xml = "<ShippingDetails>"
        shipping_xml += f"<ShippingType>{ship['ShippingType']}</ShippingType>"
        
        if "ShippingServiceOptions" in ship:
            for svc in ship["ShippingServiceOptions"]:
                shipping_xml += "<ShippingServiceOptions>"
                shipping_xml += f"<ShippingServicePriority>{svc['ShippingServicePriority']}</ShippingServicePriority>"
                shipping_xml += f"<ShippingService>{svc['ShippingService']}</ShippingService>"
                shipping_xml += f"<ShippingServiceCost>{svc['ShippingServiceCost']}</ShippingServiceCost>"
                shipping_xml += f"<ShippingServiceAdditionalCost>{svc.get('ShippingServiceAdditionalCost', 0)}</ShippingServiceAdditionalCost>"
                if svc.get('FreeShipping'):
                    shipping_xml += "<FreeShipping>true</FreeShipping>"
                if svc.get('ExpeditedService'):
                    shipping_xml += "<ExpeditedService>true</ExpeditedService>"
                shipping_xml += "</ShippingServiceOptions>"
        
        if "InternationalShippingServiceOption" in ship:
            for svc in ship["InternationalShippingServiceOption"]:
                shipping_xml += "<InternationalShippingServiceOption>"
                shipping_xml += f"<ShippingServicePriority>{svc['ShippingServicePriority']}</ShippingServicePriority>"
                shipping_xml += f"<ShippingService>{svc['ShippingService']}</ShippingService>"
                shipping_xml += f"<ShippingServiceCost>{svc['ShippingServiceCost']}</ShippingServiceCost>"
                for loc in svc.get('ShipToLocation', []):
                    shipping_xml += f"<ShipToLocation>{loc}</ShipToLocation>"
                shipping_xml += "</InternationalShippingServiceOption>"
        
        shipping_xml += "</ShippingDetails>"
    
    # 构建退货政策 XML
    return_xml = ""
    if "ReturnPolicy" in item_data:
        ret = item_data["ReturnPolicy"]
        return_xml = "<ReturnPolicy>"
        return_xml += f"<ReturnsAcceptedOption>{ret['ReturnsAcceptedOption']}</ReturnsAcceptedOption>"
        return_xml += f"<RefundOption>{ret['RefundOption']}</RefundOption>"
        return_xml += f"<ReturnsWithinOption>{ret['ReturnsWithinOption']}</ReturnsWithinOption>"
        return_xml += f"<ShippingCostPaidByOption>{ret['ShippingCostPaidByOption']}</ShippingCostPaidByOption>"
        if "Description" in ret:
            return_xml += f"<Description>{ret['Description']}</Description>"
        return_xml += "</ReturnPolicy>"
    
    # 构建完整 XML
    # 注意：Trading API 字段名和 Inventory API 不同
    xml = f"""<?xml version="1.0" encoding="utf-8"?>
<AddFixedPriceItemRequest xmlns="urn:ebay:apis:eBLBaseComponents">
    <RequesterCredentials>
        <eBayAuthToken>{USER_TOKEN}</eBayAuthToken>
    </RequesterCredentials>
    <ErrorLanguage>en_US</ErrorLanguage>
    <WarningLevel>High</WarningLevel>
    <Version>1113</Version>
    <Item>
        <Title>{item_data['Title']}</Title>
        <Description><![CDATA[{item_data['Description']}]]></Description>
        <PrimaryCategory>
            <CategoryID>{item_data['PrimaryCategory']['CategoryID']}</CategoryID>
        </PrimaryCategory>
        <CategoryMappingAllowed>true</CategoryMappingAllowed>
        <ConditionID>{item_data['ConditionID']}</ConditionID>
        <ListingDuration>{item_data['ListingDuration']}</ListingDuration>
        <StartPrice>{item_data['StartPrice']}</StartPrice>
        <BuyItNowPrice>{item_data.get('BuyItNowPrice', item_data['StartPrice'])}</BuyItNowPrice>
        <Quantity>{item_data['Quantity']}</Quantity>
        <SKU>{item_data['SKU']}</SKU>
        <ProductListingDetails>
            <UPC>{item_data.get('UPC', '')}</UPC>
        </ProductListingDetails>
        {pictures_xml}
        {item_specifics_xml}
        <Location>{item_data['Location']}</Location>
        <Country>{item_data['Country']}</Country>
        <Currency>{item_data['Currency']}</Currency>
        <PaymentMethods>{item_data['PaymentMethods'][0]}</PaymentMethods>
        {shipping_xml}
        {return_xml}
        <Site>{item_data['Site']}</Site>
        <ListingSite>{item_data.get('ListingSite', 'US')}</ListingSite>
        {'<VerifyOnly>true</VerifyOnly>' if create_draft else ''}
    </Item>
</AddFixedPriceItemRequest>
"""
    return xml


def send_trading_api_request(xml_request):
    """
    发送 Trading API 请求
    
    Args:
        xml_request: XML 字符串
    
    Returns:
        响应字典
    """
    headers = {
        "X-EBAY-API-COMPATIBILITY-LEVEL": "1113",
        "X-EBAY-API-CALL-NAME": "AddFixedPriceItem",
        "X-EBAY-API-SITEID": "0",  # US
        "X-EBAY-API-APP-NAME": APP_ID,
        "X-EBAY-API-DEV-NAME": DEV_ID,
        "X-EBAY-API-CERT-NAME": APP_SECRET,
        "X-EBAY-API-REQUEST-ENCODING": "base64",
        "Content-Type": "text/xml",
    }
    
    endpoint = get_trading_api_endpoint()
    
    print(f"发送请求到：{endpoint}")
    print(f"APP_ID: {APP_ID[:20]}...")
    
    resp = requests.post(endpoint, headers=headers, data=xml_request, timeout=60)
    
    return {
        'status_code': resp.status_code,
        'headers': dict(resp.headers),
        'body': resp.text
    }


def parse_response(xml_response):
    """
    解析 XML 响应
    
    Args:
        xml_response: XML 字符串
    
    Returns:
        响应数据字典
    """
    import xml.etree.ElementTree as ET
    
    try:
        root = ET.fromstring(xml_response)
        ns = {"ebay": "urn:ebay:apis:eBLBaseComponents"}
        
        result = {}
        
        # 提取关键字段
        ack = root.find(".//ebay:Ack", ns)
        result['Ack'] = ack.text if ack is not None else "Unknown"
        
        item_id = root.find(".//ebay:ItemID", ns)
        result['ItemID'] = item_id.text if item_id is not None else None
        
        listing_status = root.find(".//ebay:ListingStatus", ns)
        if listing_status is not None:
            status = listing_status.find("ebay:Status", ns)
            result['ListingStatus'] = status.text if status is not None else None
        
        # 提取错误信息
        errors = root.findall(".//ebay:Errors", ns)
        if errors:
            result['Errors'] = []
            for err in errors:
                error_data = {}
                code = err.find("ebay:ErrorCode", ns)
                msg = err.find("ebay:Message", ns)
                severity = err.find("ebay:SeverityCode", ns)
                if code is not None:
                    error_data['ErrorCode'] = code.text
                if msg is not None:
                    error_data['Message'] = msg.text
                if severity is not None:
                    error_data['SeverityCode'] = severity.text
                result['Errors'].append(error_data)
        
        return result
        
    except ET.ParseError as e:
        return {'Ack': 'ParseError', 'Message': str(e)}


def main():
    """主函数"""
    print("=" * 60)
    print("🔮 eBay 传统发布 API - AddFixedPriceItem")
    print("=" * 60)
    print(f"SKU: {SKU}")
    print(f"标题：{ITEM_DATA['Title'][:60]}...")
    print(f"价格：${ITEM_DATA['StartPrice']}")
    print(f"运费：${ITEM_DATA['ShippingDetails']['ShippingServiceOptions'][0]['ShippingServiceCost']}")
    print("=" * 60)
    
    # 选择模式
    print("\n请选择发布模式：")
    print("1. 创建草稿（VerifyOnly）- 不实际发布")
    print("2. 直接发布")
    print()
    
    # 默认创建草稿
    create_draft = True
    
    # 构建请求
    print("构建 AddFixedPriceItem 请求...")
    xml_request = build_add_fixed_price_item_request(ITEM_DATA, create_draft=create_draft)
    
    # 发送请求
    print("发送请求...")
    resp = send_trading_api_request(xml_request)
    
    # 解析响应
    print("解析响应...")
    result = parse_response(resp['body'])
    
    # 显示结果
    print("\n" + "=" * 60)
    print("📊 API 响应结果")
    print("=" * 60)
    print(f"Ack: {result.get('Ack', 'Unknown')}")
    
    if result.get('ItemID'):
        print(f"✅ Item ID: {result['ItemID']}")
        print(f"Listing Status: {result.get('ListingStatus', 'N/A')}")
        
        if create_draft:
            print("\n⚠️  注意：这是草稿（VerifyOnly 模式）")
            print("   商品未实际发布，仅验证了数据")
            print("   如需实际发布，请修改 create_draft=False")
        else:
            print("\n✅ 商品已成功发布！")
            print(f"   查看链接：https://www.ebay.com/itm/{result['ItemID']}")
    else:
        print("\n❌ 发布失败")
        if 'Errors' in result:
            print("\n错误信息：")
            for err in result['Errors']:
                print(f"  - [{err.get('ErrorCode', 'N/A')}] {err.get('Message', 'Unknown error')}")
    
    print("\n" + "=" * 60)
    print("原始响应（前 1000 字符）：")
    print(resp['body'][:1000])
    print("=" * 60)


if __name__ == "__main__":
    main()
