#!/usr/bin/env python3
"""
eBay Listing Generator - 自动化商品上架工具
工作流程：
1. 抓取产品页面信息
2. 调用 AI 生成 SEO 标题 + HTML 描述
3. 通过 eBay API 发布 listing

作者：Jarvis for Ariel
"""

import os
import json
import requests
from pathlib import Path
from typing import Optional, Dict, Any
import re

# ============== 配置 ==============
SCRIPT_DIR = Path(__file__).parent
CONFIG_FILE = SCRIPT_DIR / "ebay_config.json"
TEMPLATE_FILE = SCRIPT_DIR / "ebay_template.txt"

# eBay API 端点（Sandbox 环境，生产环境请修改）
EBAY_API_BASE = "https://api.sandbox.ebay.com"
EBAY_OAUTH_TOKEN_URL = "https://api.sandbox.ebay.com/identity/v1/oauth2/token"

# ============== 配置加载 ==============
def load_config() -> Dict[str, Any]:
    """加载配置文件"""
    if not CONFIG_FILE.exists():
        print(f"⚠️  配置文件不存在：{CONFIG_FILE}")
        print("请复制 ebay_config.example.json 为 ebay_config.json 并填写配置")
        return {}
    
    with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
        return json.load(f)

def load_template() -> str:
    """加载模板文件"""
    if not TEMPLATE_FILE.exists():
        # 返回默认模板
        return """以下是产品信息，按照模板《eBay Description Template 0303》生成 html 格式的英文商品介绍
（美式用词，请检查代码里不要有错误代码出现），和 seo 优化过的 ebay 标题
（标题不超过 80 个字符，并且尽可能用满 80 个字符，重点词尽可能放在前 56 个字）

输出格式：
===TITLE===
[标题内容]

===DESCRIPTION===
[HTML 描述内容]
"""
    
    with open(TEMPLATE_FILE, 'r', encoding='utf-8') as f:
        return f.read()

# ============== 网页抓取 ==============
def fetch_product_info(url: str) -> str:
    """抓取产品页面信息"""
    print(f"📥 抓取产品页面：{url}")
    
    try:
        response = requests.get(url, headers={
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'
        }, timeout=30)
        response.raise_for_status()
        
        # 简单提取文本内容
        text = response.text
        # 移除 script 和 style 标签
        text = re.sub(r'<script[^>]*>.*?</script>', '', text, flags=re.DOTALL)
        text = re.sub(r'<style[^>]*>.*?</style>', '', text, flags=re.DOTALL)
        # 移除 HTML 标签
        text = re.sub(r'<[^>]+>', ' ', text)
        # 清理空白
        text = re.sub(r'\s+', ' ', text).strip()
        
        print(f"✓ 抓取成功，内容长度：{len(text)} 字符")
        return text[:10000]  # 限制长度
    except Exception as e:
        print(f"✗ 抓取失败：{e}")
        return ""

# ============== AI 调用 ==============
def generate_listing_with_ai(product_info: str, template: str) -> tuple[str, str]:
    """调用 AI 生成标题和描述"""
    print("🤖 调用 AI 生成 listing...")
    
    # 这里调用 OpenClaw 的 sessions_spawn 或其他 AI 接口
    # 简化版本：直接返回示例（实际使用时需要接入 AI API）
    
    prompt = f"""
{template}

产品信息：
{product_info}
"""
    
    # 实际使用时，这里应该调用你的 AI 服务
    # 例如：OpenAI API, Claude API, 或本地 OpenClaw 会话
    print("⚠️  需要配置 AI API 密钥")
    print("提示：可以使用 OpenClaw 的 sessions_spawn 或直接调用 AI API")
    
    # 示例返回（需要替换为实际 AI 调用）
    title = "Sample Product Title - SEO Optimized for eBay Search Results Max 80"
    description = "<html><body><h1>Sample Description</h1></body></html>"
    
    return title, description

def generate_listing_openclaw(product_info: str) -> tuple[str, str]:
    """使用 OpenClaw 生成 listing（推荐方式）"""
    print("🤖 通过 OpenClaw 生成 listing...")
    
    prompt = f"""
以下是产品信息，按照模板生成 html 格式的英文商品介绍（美式用词，请检查代码里不要有错误代码出现），
和 seo 优化过的 ebay 标题（标题不超过 80 个字符，并且尽可能用满 80 个字符，重点词尽可能放在前 56 个字）

产品信息：
{product_info}

输出格式：
===TITLE===
[标题内容]

===DESCRIPTION===
[HTML 描述内容]
"""
    
    # 使用 OpenClaw 的 sessions_spawn 调用 AI
    # 这里简化为直接返回，实际使用时需要集成
    print("提示：此函数需要集成 OpenClaw API")
    return "", ""

# ============== eBay API ==============
def get_ebay_oauth_token(config: Dict[str, Any]) -> Optional[str]:
    """获取 eBay OAuth Token"""
    app_id = config.get('EBAY_APP_ID', '')
    app_secret = config.get('EBAY_APP_SECRET', '')
    
    if not app_id or not app_secret:
        print("⚠️  缺少 eBay API 密钥配置")
        return None
    
    try:
        response = requests.post(
            EBAY_OAUTH_TOKEN_URL,
            headers={
                'Content-Type': 'application/x-www-form-urlencoded',
                'Authorization': 'Basic ' + requests.auth._basic_auth_str(app_id, app_secret)
            },
            data={
                'grant_type': 'client_credentials',
                'scope': 'https://api.ebay.com/oauth/api_scope'
            },
            timeout=30
        )
        response.raise_for_status()
        token_data = response.json()
        print("✓ 获取 eBay Token 成功")
        return token_data.get('access_token')
    except Exception as e:
        print(f"✗ 获取 Token 失败：{e}")
        return None

def create_ebay_listing(config: Dict[str, Any], title: str, description: str, price: float, category_id: str = "1220") -> bool:
    """
    创建 eBay listing
    
    Args:
        config: 配置字典
        title: 商品标题
        description: HTML 描述
        price: 价格 (USD)
        category_id: eBay 分类 ID (默认 1220 = Stationery & Office Supplies)
    """
    token = get_ebay_oauth_token(config)
    if not token:
        return False
    
    ebay_site_id = config.get('EBAY_SITE_ID', '0')  # 0 = US
    marketplace_id = config.get('EBAY_MARKETPLACE_ID', 'EBAY_US')
    
    # 构建 listing 数据
    listing_data = {
        "title": title[:80],  # eBay 标题限制 80 字符
        "description": {
            "lang": "en-US",
            "value": description
        },
        "category": {
            "categoryId": category_id
        },
        "startPrice": {
            "currency": "USD",
            "value": str(price)
        },
        "buyItNowPrice": {
            "currency": "USD",
            "value": str(price)
        },
        "paymentMethods": ["PAYPAL", "CREDIT_CARD"],
        "shippingDetails": {
            "shippingType": "FLAT",
            "shippingServiceOptions": [{
                "shippingService": "USPSFirstClass",
                "shippingServiceCost": {
                    "currency": "USD",
                    "value": "5.00"
                },
                "shippingServicePriority": 1,
                "expeditedService": False,
                "shippingTimeMin": 3,
                "shippingTimeMax": 7
            }]
        },
        "listingDetails": {
            "listingDuration": "GTC",  # Good 'Til Cancelled
            "listingType": "FixedPrice"
        },
        "quantity": 1
    }
    
    try:
        # 使用 Trading API 添加物品
        url = f"{EBAY_API_BASE}/ws/api.dll"
        headers = {
            "X-EBAY-API-COMPATIBILITY-LEVEL": "1113",
            "X-EBAY-API-CALL-NAME": "AddItem",
            "X-EBAY-API-SITEID": ebay_site_id,
            "X-EBAY-API-REQUEST-ENCODING": "JSON",
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        }
        
        response = requests.post(url, headers=headers, json=listing_data, timeout=30)
        response.raise_for_status()
        
        result = response.json()
        
        if result.get('Ack') == 'Success':
            item_id = result.get('ItemID')
            print(f"✓ Listing 创建成功！Item ID: {item_id}")
            return True
        else:
            print(f"✗ Listing 创建失败：{result}")
            return False
            
    except Exception as e:
        print(f"✗ API 调用失败：{e}")
        return False

# ============== 主流程 ==============
def generate_and_publish(product_url: str, price: float, category_id: str = "1220") -> bool:
    """
    完整流程：抓取 → 生成 → 发布
    
    Args:
        product_url: 产品页面 URL
        price: 售价 (USD)
        category_id: eBay 分类 ID
    """
    print("=" * 50)
    print("🛒 eBay Listing Generator")
    print("=" * 50)
    
    # 1. 加载配置
    config = load_config()
    if not config:
        print("✗ 配置加载失败，请检查配置文件")
        return False
    
    # 2. 抓取产品信息
    product_info = fetch_product_info(product_url)
    if not product_info:
        print("✗ 产品信息抓取失败")
        return False
    
    # 3. 加载模板
    template = load_template()
    
    # 4. 生成 listing（调用 AI）
    # 方式 1：直接调用 AI API
    # title, description = generate_listing_with_ai(product_info, template)
    
    # 方式 2：使用 OpenClaw（推荐）
    # title, description = generate_listing_openclaw(product_info)
    
    # 临时方案：手动输入（用于测试）
    print("\n⚠️  AI 生成功能需要配置，暂时使用示例数据")
    title = f"Hobonichi 5-Year Techo Gift Edition 2026-2030 - haconiwa iyo okumi"
    description = "<html><body><h1>Product Description</h1></body></html>"
    
    # 5. 发布到 eBay
    print(f"\n📤 发布 listing...")
    print(f"标题：{title}")
    print(f"价格：${price}")
    
    success = create_ebay_listing(config, title, description, price, category_id)
    
    if success:
        print("\n✓ 发布完成！")
    else:
        print("\n✗ 发布失败")
    
    return success

# ============== CLI 入口 ==============
if __name__ == "__main__":
    import sys
    
    if len(sys.argv) < 2:
        print("用法：python ebay_listing_generator.py <产品 URL> [价格] [分类 ID]")
        print("示例：python ebay_listing_generator.py https://example.com/product 29.99 1220")
        sys.exit(1)
    
    url = sys.argv[1]
    price = float(sys.argv[2]) if len(sys.argv) > 2 else 29.99
    category_id = sys.argv[3] if len(sys.argv) > 3 else "1220"
    
    generate_and_publish(url, price, category_id)
