#!/usr/bin/env python3
"""
eBay Token Manager
管理 OAuth Token 的获取、缓存和自动刷新

核心知识点：
- OAuth Application Token 有效期固定为 2 小时（7200 秒）
- 无法手动设置或更改有效时间
- 短期有效是 eBay 的安全机制
- 最佳实践：缓存 token，2 小时内复用，过期后自动刷新
"""

import json
import time
import requests
import base64
from datetime import datetime, timedelta

class eBayTokenManager:
    """eBay OAuth Token 管理器"""
    
    def __init__(self, config_path='ebay_config.json'):
        self.config_path = config_path
        self.config = self._load_config()
        
        # Token 缓存
        self._access_token = None
        self._token_expiry = None
        self._user_token = self.config.get('OAUTH_TOKEN', '')
        
    def _load_config(self):
        """加载配置文件"""
        try:
            with open(self.config_path, 'r') as f:
                return json.load(f)
        except FileNotFoundError:
            print(f"❌ 配置文件未找到：{self.config_path}")
            return {}
    
    def _get_api_base(self):
        """获取 API 基础 URL"""
        env = self.config.get('EBAY_ENVIRONMENT', 'sandbox')
        if env == 'production':
            return 'https://api.ebay.com'
        return 'https://api.sandbox.ebay.com'
    
    def get_application_token(self):
        """
        获取 Application Token（Client Credentials）
        
        核心逻辑：
        1. 检查缓存的 token 是否有效
        2. 如果有效，直接返回复用的 token
        3. 如果过期，自动重新获取（无需用户交互）
        """
        # 检查缓存
        if self._access_token and self._token_expiry:
            # 提前 5 分钟刷新，避免边界情况
            if datetime.now() < self._token_expiry - timedelta(minutes=5):
                print(f"✓ 使用缓存的 Application Token（剩余 {int((self._token_expiry - datetime.now()).total_seconds())} 秒）")
                return self._access_token
        
        # Token 过期或不存在，重新获取
        print("🔄 Application Token 已过期/不存在，重新获取...")
        
        api_base = self._get_api_base()
        app_id = self.config.get('EBAY_APP_ID', '')
        app_secret = self.config.get('EBAY_APP_SECRET', '')
        
        # 构建 Basic Auth
        credentials = f'{app_id}:{app_secret}'
        encoded = base64.b64encode(credentials.encode()).decode()
        
        headers = {
            'Content-Type': 'application/x-www-form-urlencoded',
            'Authorization': f'Basic {encoded}'
        }
        
        # Scope 不需要区分沙盒和生产，使用相同的 scope
        scope = 'https://api.ebay.com/oauth/api_scope'
        
        data = {
            'grant_type': 'client_credentials',
            'scope': scope
        }
        
        resp = requests.post(
            f'{api_base}/identity/v1/oauth2/token',
            headers=headers,
            data=data
        )
        
        if resp.status_code != 200:
            print(f"❌ 获取 Application Token 失败：{resp.text[:200]}")
            return None
        
        token_data = resp.json()
        self._access_token = token_data.get('access_token')
        expires_in = token_data.get('expires_in', 7200)
        
        # 设置过期时间（当前时间 + 有效期）
        self._token_expiry = datetime.now() + timedelta(seconds=expires_in)
        
        print(f"✅ Application Token 获取成功")
        print(f"   Token: {self._access_token[:50]}...")
        print(f"   有效期：{expires_in} 秒（{expires_in // 60} 分钟）")
        print(f"   过期时间：{self._token_expiry.strftime('%Y-%m-%d %H:%M:%S')}")
        
        return self._access_token
    
    def get_user_token(self):
        """
        获取 User Token
        
        User Token 需要从配置文件读取（需要用户授权）
        如果过期，需要用户重新通过网页授权获取
        """
        if not self._user_token:
            print("❌ User Token 未配置")
            print("   请通过以下方式获取：")
            print("   1. 访问：https://developer.ebay.com/tools/explorer")
            print("   2. 选择环境（Sandbox/Production）")
            print("   3. 点击 'Get User Token'")
            print("   4. 登录并授权")
            print("   5. 复制 Token 到 ebay_config.json")
            return None
        
        # 简单验证 Token 格式
        if not self._user_token.startswith('v^'):
            print("⚠️  User Token 格式可能不正确（应以 v^ 开头）")
        
        print(f"✓ User Token 已加载：{self._user_token[:50]}...")
        return self._user_token
    
    def get_headers(self, use_user_token=False):
        """
        获取 API 请求头
        
        Args:
            use_user_token: 是否使用 User Token（默认为 False，使用 Application Token）
                           User Token 用于需要卖家授权的 API（如 Inventory、Sell）
                           Application Token 用于公开 API（如 Browse）
        """
        if use_user_token:
            token = self.get_user_token()
        else:
            token = self.get_application_token()
        
        if not token:
            return None
        
        return {
            'Authorization': f'Bearer {token}',
            'Content-Type': 'application/json',
            'Content-Language': 'en-US',
            'X-EBAY-C-MARKETPLACE-ID': 'EBAY_US',
            'Accept': 'application/json'
        }
    
    def test_connection(self):
        """测试 API 连接"""
        headers = self.get_headers(use_user_token=True)
        if not headers:
            return False
        
        api_base = self._get_api_base()
        resp = requests.get(
            f'{api_base}/sell/inventory/v1/inventory_item?limit=1',
            headers=headers
        )
        
        if resp.status_code == 200:
            print("✅ API 连接测试成功")
            return True
        elif resp.status_code == 401:
            print("❌ API 连接失败：Token 无效或过期")
            return False
        else:
            print(f"⚠️  API 连接测试返回：{resp.status_code}")
            print(f"   {resp.text[:200]}")
            return resp.status_code != 401


# 使用示例
if __name__ == "__main__":
    print("=" * 60)
    print("🔑 eBay Token Manager 测试")
    print("=" * 60)
    
    manager = eBayTokenManager()
    
    # 测试 Application Token
    print("\n1️⃣ 测试 Application Token")
    print("-" * 40)
    app_token = manager.get_application_token()
    
    # 等待 1 秒后再次获取（应该使用缓存）
    print("\n2️⃣ 再次获取（应使用缓存）")
    print("-" * 40)
    app_token2 = manager.get_application_token()
    
    # 测试 User Token
    print("\n3️⃣ 测试 User Token")
    print("-" * 40)
    user_token = manager.get_user_token()
    
    # 测试 API 连接
    print("\n4️⃣ 测试 API 连接")
    print("-" * 40)
    manager.test_connection()
    
    print("\n" + "=" * 60)
    print("✅ 测试完成")
    print("=" * 60)
