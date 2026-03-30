# 🔑 eBay OAuth Token 管理知识

**学习时间：** 2026-03-12  
**来源：** eBay 开发者文档 + 实践经验

---

## 📌 核心知识点

### Token 有效期

| Token 类型 | 有效期 | 刷新方式 |
|------------|--------|----------|
| **Application Token** | 2 小时（7200 秒） | 自动刷新（无需用户交互） |
| **User Token** | 约 1 小时 | 需要用户重新授权 |

⚠️ **重要：**
- 有效期固定为 2 小时，无法手动设置或更改
- 短期有效是 eBay 强制执行的安全机制
- 防止 Token 泄露后被长期滥用

---

## 🔄 Token 生命周期

### Application Token（Client Credentials）

```
┌─────────────┐
│ 首次请求    │ ──→ 获取 Token（有效期 2 小时）
└─────────────┘
       ↓
┌─────────────┐
│ 缓存 Token  │ ──→ 后续 API 调用复用
└─────────────┘
       ↓
┌─────────────┐
│ 检查过期    │ ──→ 剩余 < 5 分钟？
└─────────────┘
       ↓
   ┌───┴───┐
   │       │
  是      否
   │       │
   ↓       ↓
┌─────┐ ┌──────┐
│ 刷新 │ │ 复用 │
└─────┘ └──────┘
```

### User Token

```
用户授权 → 获取 Token → 使用 → 过期 → 重新授权
                        ↓
                   返回 1001 错误
```

---

## ✅ 最佳实践

### 1. 缓存并复用 Token

❌ **错误做法：**
```python
# 每次 API 调用都重新获取 Token
for item in items:
    token = get_token()  # 浪费！
    api_call(token)
```

✅ **正确做法：**
```python
# 获取一次，复用 2 小时
token = get_token()
for item in items:
    api_call(token)  # 复用
```

### 2. 自动刷新机制

```python
class TokenManager:
    def __init__(self):
        self.token = None
        self.expiry = None
    
    def get_token(self):
        # 检查缓存
        if self.token and self.expiry:
            if datetime.now() < self.expiry - timedelta(minutes=5):
                return self.token  # 复用缓存
        
        # 过期了，重新获取
        self.token = fetch_new_token()
        self.expiry = datetime.now() + timedelta(seconds=7200)
        return self.token
```

### 3. 错误处理

```python
def api_call():
    token = get_token()
    resp = requests.get(url, headers={'Authorization': f'Bearer {token}'})
    
    if resp.status_code == 401 and resp.json().get('errorId') == 1001:
        # Token 过期，刷新后重试
        token = refresh_token()
        resp = requests.get(url, headers={'Authorization': f'Bearer {token}'})
    
    return resp
```

---

## 📊 Token 类型对比

| 特性 | Application Token | User Token |
|------|------------------|------------|
| **获取方式** | Client Credentials | User Authorization |
| **需要用户交互** | ❌ 否 | ✅ 是 |
| **有效期** | 2 小时 | ~1 小时 |
| **用途** | 公开 API（Browse、Catalog） | 卖家 API（Inventory、Sell） |
| **自动刷新** | ✅ 可以 | ❌ 需要重新授权 |
| **Scope** | `oauth/api_scope` | `sell.inventory.*` 等 |

---

## 🛠️ 实现代码

### Token Manager 类

```python
import requests
import base64
from datetime import datetime, timedelta

class eBayTokenManager:
    def __init__(self, app_id, app_secret):
        self.app_id = app_id
        self.app_secret = app_secret
        self._token = None
        self._expiry = None
    
    def get_application_token(self):
        # 检查缓存
        if self._token and self._expiry:
            if datetime.now() < self._expiry - timedelta(minutes=5):
                return self._token
        
        # 重新获取
        credentials = f'{self.app_id}:{self.app_secret}'
        encoded = base64.b64encode(credentials.encode()).decode()
        
        resp = requests.post(
            'https://api.ebay.com/identity/v1/oauth2/token',
            headers={
                'Content-Type': 'application/x-www-form-urlencoded',
                'Authorization': f'Basic {encoded}'
            },
            data={
                'grant_type': 'client_credentials',
                'scope': 'https://api.ebay.com/oauth/api_scope'
            }
        )
        
        token_data = resp.json()
        self._token = token_data['access_token']
        self._expiry = datetime.now() + timedelta(seconds=7200)
        
        return self._token
```

---

## ⚠️ 常见错误

### 错误 1001: Invalid Access Token

**原因：** Token 过期

**解决：**
```python
if resp.status_code == 401:
    error = resp.json().get('errors', [{}])[0]
    if error.get('errorId') == 1001:
        # Token 过期，刷新
        token = refresh_token()
        # 重试请求
```

### 错误：每次调用都刷新 Token

**问题：** 性能差，可能被限流

**解决：** 缓存 Token，2 小时内复用

---

## 📋 检查清单

开发 eBay API 应用时，确认：

- [ ] Token 已缓存（内存/静态变量）
- [ ] 复用缓存 Token（不每次刷新）
- [ ] 提前 5 分钟刷新（避免边界情况）
- [ ] 处理 1001 错误（自动刷新重试）
- [ ] Application Token 和 User Token 分开管理
- [ ] User Token 过期时提示用户重新授权

---

## 🔗 相关资源

- eBay OAuth 文档：https://developer.ebay.com/api-concepts/authentication
- Token 刷新示例：https://developer.ebay.com/api-concepts/authentication/token-refresh
- API Explorer：https://developer.ebay.com/tools/explorer

---

**最后更新：** 2026-03-12  
**状态：** ✅ 已应用到 `ebay_token_manager.py`
