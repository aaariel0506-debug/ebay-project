"""
auth/ebay_oauth.py — eBay OAuth 2.0 授权流程

用法（命令行）：
    python main.py auth

流程：
1. 在本地启动 HTTP 服务器（默认端口 8080）监听回调
2. 在浏览器打开 eBay 授权页面
3. 用户授权后，eBay 重定向到 http://localhost:8080/callback?code=...
4. 自动交换 code 获取 access_token + refresh_token
5. 保存 token 到 config.yaml

前置条件（eBay Developer Console 配置）：
- 在 https://developer.ebay.com/my/keys 选择 Production App
- 在 "User Tokens" / "OAuth Redirect URL" 中添加：
    http://localhost:8080/callback
  （也称为 RuName 或 Redirect URI）
- 记下 RuName（格式：YourName-YourApp-Production-xxxxxxxx）
"""
import base64
import json
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlparse

import requests
import yaml


# eBay OAuth 端点
EBAY_AUTH_URL = "https://auth.ebay.com/oauth2/authorize"
EBAY_TOKEN_URL = "https://api.ebay.com/identity/v1/oauth2/token"

# 所需权限范围
SCOPES = [
    "https://api.ebay.com/oauth/api_scope",
    "https://api.ebay.com/oauth/api_scope/sell.fulfillment.readonly",
    "https://api.ebay.com/oauth/api_scope/sell.finances",
]

CONFIG_PATH = Path(__file__).parent.parent / "config.yaml"
CALLBACK_PORT = 8080
CALLBACK_PATH = "/callback"


def _load_config() -> dict:
    if CONFIG_PATH.exists():
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    return {}


def _save_config(cfg: dict) -> None:
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        yaml.dump(cfg, f, allow_unicode=True, default_flow_style=False, sort_keys=False)


def _build_auth_header(client_id: str, client_secret: str) -> str:
    """生成 Basic Auth 头（base64 编码的 client_id:client_secret）"""
    credentials = f"{client_id}:{client_secret}"
    encoded = base64.b64encode(credentials.encode()).decode()
    return f"Basic {encoded}"


def get_ebay_credentials() -> dict | None:
    """从 config.yaml 读取 eBay API 凭据"""
    cfg = _load_config()
    return cfg.get("ebay_api")


def refresh_access_token(client_id: str, client_secret: str, refresh_token: str) -> str | None:
    """
    用 refresh_token 换取新的 access_token（access_token 2小时过期，refresh_token 18个月）

    Returns:
        新的 access_token，失败返回 None
    """
    headers = {
        "Content-Type": "application/x-www-form-urlencoded",
        "Authorization": _build_auth_header(client_id, client_secret),
    }
    data = {
        "grant_type": "refresh_token",
        "refresh_token": refresh_token,
        "scope": " ".join(SCOPES),
    }
    resp = requests.post(EBAY_TOKEN_URL, headers=headers, data=data, timeout=30)
    if resp.status_code == 200:
        token_data = resp.json()
        # 更新 config.yaml 中的 access_token
        cfg = _load_config()
        cfg.setdefault("ebay_api", {})["access_token"] = token_data["access_token"]
        _save_config(cfg)
        return token_data["access_token"]
    else:
        print(f"[auth] Refresh token 失败: {resp.status_code} {resp.text}")
        return None


def get_valid_access_token() -> str | None:
    """
    返回有效的 access_token（如有需要自动刷新）

    Returns:
        access_token 字符串，失败返回 None
    """
    creds = get_ebay_credentials()
    if not creds:
        return None

    client_id = creds.get("client_id") or creds.get("app_id")
    client_secret = creds.get("client_secret") or creds.get("cert_id")
    access_token = creds.get("access_token")
    refresh_token = creds.get("refresh_token")

    # 先尝试直接用 access_token；如果过期，用 refresh_token 换新的
    if access_token:
        return access_token
    if refresh_token and client_id and client_secret:
        return refresh_token(client_id, client_secret, refresh_token)

    return None


def run_oauth_flow(client_id: str, client_secret: str, ru_name: str) -> dict:
    """
    执行完整 OAuth 授权码流程：
    1. 本地启动 HTTP 回调服务器
    2. 打开浏览器到 eBay 授权页面
    3. 接收回调中的 code
    4. 用 code 换取 access_token + refresh_token
    5. 保存到 config.yaml

    Args:
        client_id:     App ID（Client ID）
        client_secret: Cert ID（Client Secret）
        ru_name:       在 eBay 注册的 Redirect URL Name

    Returns:
        {"access_token": ..., "refresh_token": ..., "expires_in": ...}
    """
    auth_code_holder = {"code": None, "error": None}
    server_ready = threading.Event()

    class CallbackHandler(BaseHTTPRequestHandler):
        def do_GET(self):
            parsed = urlparse(self.path)
            if parsed.path != CALLBACK_PATH:
                self.send_response(404)
                self.end_headers()
                return

            params = parse_qs(parsed.query)

            if "code" in params:
                auth_code_holder["code"] = params["code"][0]
                body = b"""
                <html><body style="font-family:sans-serif;text-align:center;margin-top:100px">
                <h2>&#10003; eBay \u6388\u6743\u6210\u529f\uff01</h2>
                <p>\u53ef\u4ee5\u5173\u95ed\u6b64\u7a97\u53e3\u5e76\u8fd4\u56de\u7ec8\u7aef\u3002</p>
                </body></html>
                """
            elif "error" in params:
                auth_code_holder["error"] = params.get("error_description", ["Unknown error"])[0]
                body = b"""
                <html><body style="font-family:sans-serif;text-align:center;margin-top:100px">
                <h2>&#10007; \u6388\u6743\u5931\u8d25</h2>
                <p>\u8bf7\u8fd4\u56de\u7ec8\u7aef\u67e5\u770b\u9519\u8bef\u4fe1\u606f\u3002</p>
                </body></html>
                """
            else:
                body = b"<html><body>No code received.</body></html>"

            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(body)

            # 通知主线程
            server_ready.set()

        def log_message(self, format, *args):
            pass  # 静默日志

    # 启动本地 HTTP 服务器
    server = HTTPServer(("localhost", CALLBACK_PORT), CallbackHandler)
    server_thread = threading.Thread(target=server.serve_forever, daemon=True)
    server_thread.start()

    redirect_uri = f"http://localhost:{CALLBACK_PORT}{CALLBACK_PATH}"

    # 构建授权 URL
    auth_params = {
        "client_id": client_id,
        "redirect_uri": ru_name,        # eBay 要求传 RuName，不是实际 URL
        "response_type": "code",
        "scope": " ".join(SCOPES),
        "state": "ebay_tax_system",
    }
    auth_url = f"{EBAY_AUTH_URL}?{urlencode(auth_params)}"

    print(f"\n[auth] 正在打开浏览器进行 eBay 授权...")
    print(f"[auth] 如浏览器未自动打开，请手动访问：\n  {auth_url}\n")
    webbrowser.open(auth_url)

    # 等待回调（最多 120 秒）
    print("[auth] 等待 eBay 授权回调（请在浏览器中完成授权）...")
    got_callback = server_ready.wait(timeout=120)
    server.shutdown()

    if not got_callback or auth_code_holder["error"]:
        error_msg = auth_code_holder.get("error") or "超时未收到授权回调"
        raise RuntimeError(f"OAuth 授权失败: {error_msg}")

    if not auth_code_holder["code"]:
        raise RuntimeError("未收到授权码")

    # 用 code 换取 access_token
    print("[auth] 正在用授权码换取 access_token...")
    headers = {
        "Content-Type": "application/x-www-form-urlencoded",
        "Authorization": _build_auth_header(client_id, client_secret),
    }
    data = {
        "grant_type": "authorization_code",
        "code": auth_code_holder["code"],
        "redirect_uri": ru_name,
    }
    resp = requests.post(EBAY_TOKEN_URL, headers=headers, data=data, timeout=30)
    if resp.status_code != 200:
        raise RuntimeError(f"Token 交换失败: {resp.status_code} {resp.text}")

    token_data = resp.json()

    # 保存到 config.yaml
    cfg = _load_config()
    cfg.setdefault("ebay_api", {}).update({
        "client_id": client_id,
        "client_secret": client_secret,
        "ru_name": ru_name,
        "access_token": token_data["access_token"],
        "refresh_token": token_data.get("refresh_token", ""),
        "expires_in": token_data.get("expires_in", 7200),
    })
    _save_config(cfg)

    print("[auth] ✓ Token 已保存到 config.yaml")
    return token_data
