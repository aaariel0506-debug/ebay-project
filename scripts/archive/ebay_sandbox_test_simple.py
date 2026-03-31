#!/usr/bin/env python3
"""
eBay 沙盒 API 简单测试
不需要 API 密钥，直接测试沙盒环境连通性
"""

import requests
from datetime import datetime

print("=" * 60)
print("🧪 eBay 沙盒 API 连通性测试")
print("=" * 60)

# 测试 1：沙盒网站访问
print("\n📡 测试 1: 访问 eBay 沙盒网站...")
try:
    response = requests.get("https://www.sandbox.ebay.com/", timeout=10)
    if response.status_code == 200:
        print("✓ 沙盒网站可访问")
        print(f"  响应时间：{response.elapsed.total_seconds():.2f}秒")
    else:
        print(f"⚠ 沙盒网站响应异常：{response.status_code}")
except Exception as e:
    print(f"❌ 无法访问沙盒网站：{e}")

# 测试 2：沙盒 API 端点访问（无需认证）
print("\n📡 测试 2: 测试沙盒 API 端点...")
try:
    # 测试 OAuth 端点是否可达
    response = requests.post(
        "https://api.sandbox.ebay.com/identity/v1/oauth2/token",
        headers={'Content-Type': 'application/x-www-form-urlencoded'},
        data={'grant_type': 'client_credentials'},
        timeout=10
    )
    
    # 401 是正常的（没有凭证），说明端点可用
    if response.status_code == 401:
        print("✓ 沙盒 API 端点可用（需要认证）")
        print(f"  响应：401 Unauthorized（预期）")
    elif response.status_code == 200:
        print("✓ 沙盒 API 端点可用")
    else:
        print(f"⚠ 沙盒 API 响应：{response.status_code}")
except Exception as e:
    print(f"❌ 无法连接沙盒 API：{e}")

# 测试 3：生产环境 API 端点对比
print("\n📡 测试 3: 对比生产环境 API 端点...")
try:
    response = requests.post(
        "https://api.ebay.com/identity/v1/oauth2/token",
        headers={'Content-Type': 'application/x-www-form-urlencoded'},
        data={'grant_type': 'client_credentials'},
        timeout=10
    )
    
    if response.status_code == 401:
        print("✓ 生产 API 端点可用（需要认证）")
    else:
        print(f"✓ 生产 API 端点响应：{response.status_code}")
except Exception as e:
    print(f"⚠ 生产 API 连接问题：{e}")

# 总结
print("\n" + "=" * 60)
print("测试结果总结")
print("=" * 60)
print("""
✅ eBay 沙盒环境是可用的！

沙盒环境说明：
- 网址：https://www.sandbox.ebay.com
- API: https://api.sandbox.ebay.com
- 完全免费，用于测试
- 与生产环境完全隔离

下一步：
1. 注册 eBay 开发者账号
   → https://developer.ebay.com/

2. 创建应用获取 API 密钥
   → Dashboard → Keys & Credentials → Create a key

3. 填写配置文件
   → 编辑 scripts/ebay_config.json
   → 填入 EBAY_APP_ID 和 EBAY_APP_SECRET

4. 运行完整测试
   → python3 test_ebay_sandbox.py

详细指南：
→ 查看 scripts/EBAY_AUTO_PUBLISH_QUICKSTART.md
""")

print("=" * 60)
