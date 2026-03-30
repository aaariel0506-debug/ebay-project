#!/usr/bin/env python3
"""
eBay Merchant Location 创建工具
================================
用法：python3 ebay_create_location.py

会交互式询问地址信息，创建成功后自动写入 config.json
"""

import json
import sys
from pathlib import Path

# 添加路径
sys.path.insert(0, str(Path(__file__).parent))
from ebay_automation.ebay_client import EbayClient

CONFIG_PATH = Path(__file__).parent / "ebay_automation" / "config.json"


def load_config():
    with open(CONFIG_PATH) as f:
        return json.load(f)


def save_config(config):
    with open(CONFIG_PATH, "w") as f:
        json.dump(config, f, indent=2, ensure_ascii=False)


def list_locations(client):
    """查询已有的 Location"""
    print("\n正在查询已有 Merchant Location...")
    resp = client.get("/sell/inventory/v1/location")
    if resp.ok:
        locations = resp.body.get("locations", [])
        if locations:
            print(f"  找到 {len(locations)} 个已有 Location：")
            for loc in locations:
                key = loc.get("merchantLocationKey", "")
                name = loc.get("name", "")
                status = loc.get("merchantLocationStatus", "")
                print(f"    - key: {key}  name: {name}  status: {status}")
            return locations
        else:
            print("  没有找到已有 Location，将创建新的。")
            return []
    else:
        print(f"  查询失败（{resp.status_code}）：{str(resp.body)[:200]}")
        return []


def create_location(client):
    """交互式创建 Merchant Location"""

    print()
    print("=" * 55)
    print("  创建 Merchant Location（发货仓库地址）")
    print("=" * 55)
    print()
    print("请填写你的发货地址（美国地址）：")
    print()

    # 收集地址信息
    location_key = input("  Location Key（自定义标识符，如 main-warehouse）: ").strip()
    if not location_key:
        location_key = "main-warehouse"

    location_name = input(f"  Location 名称（如 Main Warehouse）[默认: Main Warehouse]: ").strip()
    if not location_name:
        location_name = "Main Warehouse"

    print()
    print("  选择国家：")
    print("  1. 日本 (JP)")
    print("  2. 美国 (US)")
    print("  3. 其他")
    country_choice = input("  输入编号 [默认: 1 日本]: ").strip()

    if country_choice == "2":
        country = "US"
        country_label = "美国"
    elif country_choice == "3":
        country = input("  输入国家代码（如 CN / GB / DE）: ").strip().upper()
        country_label = country
    else:
        country = "JP"
        country_label = "日本"

    print()
    print(f"  地址信息（{country_label}）：")
    address_line1 = input("  地址行1（番地・建物名など / Street address）: ").strip()
    address_line2 = input("  地址行2（可选）: ").strip()
    city = input("  市区町村 / City: ").strip()

    if country == "JP":
        state = input("  都道府県（如 Tokyo / Osaka / Kanagawa）: ").strip()
        postal_code = input("  郵便番号（如 1500001）: ").strip().replace("-", "")
    else:
        state = input("  州/省（State/Province）: ").strip()
        postal_code = input("  邮编（Postal Code）: ").strip()

    print()
    print(f"  即将创建：")
    print(f"    Key:     {location_key}")
    print(f"    Name:    {location_name}")
    print(f"    Address: {address_line1}")
    if address_line2:
        print(f"             {address_line2}")
    print(f"             {city}, {state} {postal_code}, {country}")
    print()

    confirm = input("  确认创建？(y/n): ").strip().lower()
    if confirm != "y":
        print("  已取消。")
        return None

    # 构建请求体
    address = {
        "addressLine1": address_line1,
        "city": city,
        "postalCode": postal_code,
        "country": country
    }
    if address_line2:
        address["addressLine2"] = address_line2
    if state:
        address["stateOrProvince"] = state

    body = {
        "location": {"address": address},
        "name": location_name,
        "merchantLocationStatus": "ENABLED",
        "locationTypes": ["WAREHOUSE"]
    }

    # 发送 POST 请求
    print()
    print(f"  正在创建 Location '{location_key}'...")
    resp = client.post(f"/sell/inventory/v1/location/{location_key}", data=body)

    if resp.ok or resp.status_code == 204:
        print(f"  ✅ Location 创建成功！")
        print(f"     merchantLocationKey = {location_key}")
        return location_key
    else:
        print(f"  ❌ 创建失败（{resp.status_code}）：")
        print(f"     {json.dumps(resp.body, ensure_ascii=False, indent=4)}")
        print()
        print("  常见原因：")
        print("  - 地址不是真实的美国地址（eBay 会校验）")
        print("  - Location Key 包含非法字符（只能用字母、数字、连字符）")
        print("  - Token 权限不足（需要 sell.inventory scope）")
        return None


def main():
    print()
    print("=" * 55)
    print("  eBay Merchant Location 配置工具")
    print("=" * 55)

    client = EbayClient(str(CONFIG_PATH))

    # 先查有没有现成的
    locations = list_locations(client)

    if locations:
        print()
        use_existing = input("是否使用已有 Location？输入 key 或直接回车新建: ").strip()
        if use_existing:
            # 使用已有的
            config = load_config()
            config["merchant_location_key"] = use_existing
            save_config(config)
            print(f"\n  ✅ 已将 merchant_location_key 设为: {use_existing}")
            print(f"     已写入 config.json")
            return

    # 创建新的
    location_key = create_location(client)

    if location_key:
        # 写入 config
        config = load_config()
        config["merchant_location_key"] = location_key
        save_config(config)
        print()
        print(f"  ✅ merchant_location_key 已写入 config.json: {location_key}")
        print()
        print("  下一步：可以开始创建 Listing 了！")


if __name__ == "__main__":
    main()
