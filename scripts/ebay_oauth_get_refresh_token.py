#!/usr/bin/env python3
"""
eBay OAuth 授权码流程 - 获取 Refresh Token
==========================================

使用方法：
  第一步：python3 ebay_oauth_get_refresh_token.py auth-url
          → 生成授权链接，在浏览器中打开

  第二步：python3 ebay_oauth_get_refresh_token.py exchange "授权码"
          → 用授权码换取 access_token + refresh_token

需要的配置（从 ebay_automation/config.json 读取）：
  - production.app_id
  - production.app_secret
  - production.dev_id
"""

import json
import sys
import base64
import requests
from pathlib import Path
from urllib.parse import quote, urlparse, parse_qs
from datetime import datetime


# ===================== 配置 =====================

CONFIG_PATH = Path(__file__).parent / "ebay_automation" / "config.json"

# 你的 RuName（在 eBay Developer Portal → Application Keys → OAuth Redirect Settings 里）
# 格式通常是：Masakiyo-Masaki-orderinf-kbqdxgpnw
# 请替换为你的实际 RuName：
RUNAME = "Masakiyo_Co.__L-Masakiyo-orderi-jucqe"

# eBay 生产环境端点
AUTH_URL = "https://auth.ebay.com/oauth2/authorize"
TOKEN_URL = "https://api.ebay.com/identity/v1/oauth2/token"

# 需要的权限范围
SCOPES = [
    "https://api.ebay.com/oauth/api_scope",
    "https://api.ebay.com/oauth/api_scope/sell.inventory",
    "https://api.ebay.com/oauth/api_scope/sell.account",
    "https://api.ebay.com/oauth/api_scope/sell.fulfillment",
    "https://api.ebay.com/oauth/api_scope/sell.marketing",
    "https://api.ebay.com/oauth/api_scope/commerce.identity.readonly",
]


def load_config():
    """加载配置文件"""
    if not CONFIG_PATH.exists():
        print(f"  配置文件不存在: {CONFIG_PATH}")
        sys.exit(1)
    with open(CONFIG_PATH, "r") as f:
        return json.load(f)


def save_config(config):
    """保存配置文件"""
    with open(CONFIG_PATH, "w") as f:
        json.dump(config, f, indent=2, ensure_ascii=False)
    print(f"  配置已保存到: {CONFIG_PATH}")


def get_credentials(config):
    """获取生产环境凭据"""
    prod = config.get("production", {})
    app_id = prod.get("app_id", "")
    app_secret = prod.get("app_secret", "")
    if not app_id or not app_secret:
        print("  生产环境 app_id 或 app_secret 未配置")
        sys.exit(1)
    return app_id, app_secret


# ===================== 第一步：生成授权 URL =====================

def generate_auth_url():
    """生成 eBay OAuth 授权 URL"""
    config = load_config()
    app_id, _ = get_credentials(config)

    if not RUNAME:
        print("=" * 60)
        print("  RuName 未设置！")
        print("=" * 60)
        print()
        print("请先在脚本顶部设置 RUNAME 变量。")
        print()
        print("查找方法：")
        print("  1. 登录 https://developer.ebay.com/my/keys")
        print("  2. 找到 Production 那一栏")
        print("  3. 点击 'User Tokens' 或 'OAuth Redirect Settings'")
        print("  4. 你的 RuName 显示在页面上")
        print()
        print("RuName 的格式类似于：")
        print("  Masakiyo-Masaki-orderinf-kbqdxgpnw")
        print()

        # 也提供交互式输入
        runame_input = input("或者直接在这里输入你的 RuName: ").strip()
        if runame_input:
            return _build_auth_url(app_id, runame_input)
        sys.exit(1)

    return _build_auth_url(app_id, RUNAME)


def _build_auth_url(app_id, runame):
    """构建授权 URL"""
    scope_str = quote(" ".join(SCOPES))

    url = (
        f"{AUTH_URL}"
        f"?client_id={app_id}"
        f"&redirect_uri={runame}"
        f"&response_type=code"
        f"&scope={scope_str}"
    )

    print()
    print("=" * 60)
    print("  第一步：在浏览器中打开以下链接")
    print("=" * 60)
    print()
    print(url)
    print()
    print("=" * 60)
    print()
    print("操作步骤：")
    print("  1. 复制上面的链接，在浏览器中打开")
    print("  2. 用你的 eBay 卖家账号登录")
    print("  3. 点击「同意」授权")
    print("  4. 页面会跳转到你设置的回调地址")
    print("  5. 从跳转后的 URL 中复制 code= 后面的值")
    print()
    print("  示例 URL:")
    print("  https://你的回调地址/?code=v%5E1.1%23i...（很长的一串）")
    print()
    print("  你需要复制的是 code= 后面的全部内容")
    print("  （如果 URL 里有 &expires_in=... 不要复制那部分）")
    print()
    print("拿到 code 后，运行：")
    print(f"  python3 {Path(__file__).name} exchange \"你的授权码\"")
    print()

    return url


# ===================== 第二步：用授权码换 Token =====================

def exchange_code(auth_code):
    """用授权码交换 access_token + refresh_token"""
    config = load_config()
    app_id, app_secret = get_credentials(config)

    runame = RUNAME
    if not runame:
        runame = input("请输入你的 RuName: ").strip()
        if not runame:
            print("  RuName 不能为空")
            sys.exit(1)

    # URL 解码授权码（如果是 URL 编码的）
    from urllib.parse import unquote
    auth_code = unquote(auth_code.strip())

    # 构建 Basic Auth
    credentials = base64.b64encode(f"{app_id}:{app_secret}".encode()).decode()

    print()
    print("=" * 60)
    print("  第二步：用授权码换取 Token")
    print("=" * 60)
    print()
    print(f"  App ID: {app_id}")
    print(f"  RuName: {runame}")
    print(f"  授权码: {auth_code[:50]}...")
    print()

    # 发送请求
    resp = requests.post(
        TOKEN_URL,
        headers={
            "Content-Type": "application/x-www-form-urlencoded",
            "Authorization": f"Basic {credentials}",
        },
        data={
            "grant_type": "authorization_code",
            "code": auth_code,
            "redirect_uri": runame,
        },
        timeout=30,
    )

    print(f"  HTTP 状态码: {resp.status_code}")
    print()

    if resp.status_code != 200:
        print("  Token 获取失败！")
        print(f"  错误信息: {resp.text[:500]}")
        print()
        print("  常见原因：")
        print("  - 授权码已过期（有效期很短，拿到后要立即使用）")
        print("  - 授权码已经用过一次（只能用一次）")
        print("  - RuName 不匹配")
        print("  - App Secret (Cert ID) 不正确")
        print()
        print("  解决方法：重新运行 auth-url 命令，再次授权获取新的 code")
        sys.exit(1)

    data = resp.json()

    access_token = data.get("access_token", "")
    refresh_token = data.get("refresh_token", "")
    expires_in = data.get("expires_in", 0)
    refresh_expires_in = data.get("refresh_token_expires_in", 0)

    print("  Token 获取成功！")
    print()
    print(f"  Access Token:  {access_token[:60]}...")
    print(f"  有效期:        {expires_in} 秒 ({expires_in // 3600} 小时)")
    print()

    if refresh_token:
        print(f"  Refresh Token: {refresh_token[:60]}...")
        print(f"  有效期:        {refresh_expires_in} 秒 ({refresh_expires_in // 86400} 天)")
        print()

        # 自动保存到配置文件
        config["oauth"]["user_token"] = access_token
        config["oauth"]["refresh_token"] = refresh_token
        config["oauth"]["refresh_token_expiry"] = (
            datetime.now().isoformat() + f" (+{refresh_expires_in // 86400} days)"
        )
        save_config(config)

        print()
        print("  已自动保存到 config.json：")
        print("    oauth.user_token     → 新的 Access Token")
        print("    oauth.refresh_token  → Refresh Token")
        print()
        print("  之后 Token 过期时，ebay_client.py 会自动")
        print("  使用 Refresh Token 静默续期，无需手动操作。")
    else:
        print("  注意：响应中没有 Refresh Token！")
        print("  这说明你可能选择的是 Auth'n'Auth 方式而非 OAuth。")
        print("  请重新操作，确保选择 OAuth (new security)。")
        print()
        print("  完整响应：")
        print(json.dumps(data, indent=2))

    print()
    print("=" * 60)
    print("  完成！")
    print("=" * 60)

    return data


# ===================== 工具：测试 Refresh Token =====================

def test_refresh():
    """测试 Refresh Token 是否可以正常续期"""
    config = load_config()
    app_id, app_secret = get_credentials(config)
    refresh_token = config.get("oauth", {}).get("refresh_token", "")

    if not refresh_token:
        print("  Refresh Token 未配置，请先运行 auth-url → exchange 流程")
        sys.exit(1)

    credentials = base64.b64encode(f"{app_id}:{app_secret}".encode()).decode()
    scopes = config.get("oauth", {}).get("scopes", SCOPES)

    print()
    print("=" * 60)
    print("  测试 Refresh Token 续期")
    print("=" * 60)
    print()
    print(f"  Refresh Token: {refresh_token[:50]}...")
    print()

    resp = requests.post(
        TOKEN_URL,
        headers={
            "Content-Type": "application/x-www-form-urlencoded",
            "Authorization": f"Basic {credentials}",
        },
        data={
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
            "scope": " ".join(scopes),
        },
        timeout=30,
    )

    print(f"  HTTP 状态码: {resp.status_code}")

    if resp.status_code == 200:
        data = resp.json()
        new_token = data.get("access_token", "")
        expires_in = data.get("expires_in", 0)
        print()
        print("  Refresh Token 续期成功！")
        print(f"  新 Access Token: {new_token[:60]}...")
        print(f"  有效期: {expires_in} 秒 ({expires_in // 3600} 小时)")

        # 更新配置
        config["oauth"]["user_token"] = new_token
        save_config(config)
        print("  新 Token 已保存到 config.json")
    else:
        print()
        print(f"  续期失败: {resp.text[:300]}")
        print("  Refresh Token 可能已过期，需要重新授权。")

    print()


# ===================== 主入口 =====================

def main():
    if len(sys.argv) < 2:
        print()
        print("eBay OAuth Refresh Token 获取工具")
        print("=" * 40)
        print()
        print("用法：")
        print(f"  python3 {Path(__file__).name} auth-url              # 生成授权链接")
        print(f"  python3 {Path(__file__).name} exchange \"授权码\"     # 用授权码换 Token")
        print(f"  python3 {Path(__file__).name} test-refresh          # 测试 Refresh Token")
        print()
        sys.exit(0)

    cmd = sys.argv[1].lower()

    if cmd == "auth-url":
        generate_auth_url()
    elif cmd == "exchange":
        if len(sys.argv) < 3:
            print("  请提供授权码：")
            print(f"  python3 {Path(__file__).name} exchange \"v%5E1.1...\"")
            sys.exit(1)
        exchange_code(sys.argv[2])
    elif cmd == "test-refresh":
        test_refresh()
    else:
        print(f"  未知命令: {cmd}")
        print(f"  可用命令: auth-url, exchange, test-refresh")


if __name__ == "__main__":
    main()
