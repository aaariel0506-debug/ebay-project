# 🔑 eBay API 权限问题解决方案

## 当前状态

| API | 状态 | 说明 |
|-----|------|------|
| Client Token | ✅ 成功 | API 密钥正确 |
| User Token | ✅ 已获取 | Token 有效 |
| Trading API (GetAccount) | ✅ 成功 | **卖家账号已激活** |
| Inventory API | ⚠️ 404 | API 可用，但无数据 |
| Sell API | ❌ 403 | 权限不足 |

---

## ✅ 好消息

**卖家账号已激活！** Trading API 可以正常使用。

---

## ⚠️ 问题原因

Sell/Inventory API 返回 403/404 的可能原因：

### 原因 1: User Token 权限范围不足
User Token 需要授权以下 scopes：
- `https://api.ebay.com/oauth/api_scope`
- `https://api.ebay.com/oauth/api_scope/sell.inventory`
- `https://api.ebay.com/oauth/api_scope/sell.account`

### 原因 2: 沙盒环境同步延迟
沙盒账号权限同步可能需要 30-60 分钟

### 原因 3: API 端点需要额外 Header
某些 API 需要特定的 Header

---

## 🔧 解决方案

### 方案 A: 重新获取 User Token（推荐）

1. 访问：https://developer.ebay.com/tools/explorer

2. 选择 "Get User Token"

3. 环境选择：**Sandbox**

4. 点击 "Get Token"

5. **重要：** 授权时确保勾选所有权限：
   - ☑ View and manage your eBay inventory
   - ☑ Manage your eBay account
   - ☑ List items and manage orders

6. 复制新 Token

7. 更新配置文件：
```bash
nano ebay_config.json
```

```json
{
  "OAUTH_TOKEN": "新的 Token"
}
```

8. 重新测试：
```bash
python3 test_sell_api_final.py
```

---

### 方案 B: 使用 Trading API 发布 Listing

既然 Trading API 可用，可以使用它来发布 Listing：

```bash
python3 test_trading_api_fixed.py
```

Trading API 是 eBay 的传统 API，功能完整但使用 XML 格式。

---

### 方案 C: 等待权限同步

如果是刚激活的账号，可能需要等待：

1. 等待 30-60 分钟
2. 重新测试

---

### 方案 D: 检查沙盒账号状态

1. 登录沙盒 eBay: https://www.sandbox.ebay.com
2. 点击 "Sell"
3. 检查是否有卖家限制或警告
4. 如果有，按提示完成

---

## 🔍 验证步骤

### 步骤 1: 验证 User Token 权限

运行以下命令检查 Token 信息：

```bash
python3 -c "
import requests
import json

with open('ebay_config.json') as f:
    config = json.load(f)

token = config['OAUTH_TOKEN']

response = requests.get(
    'https://api.sandbox.ebay.com/identity/v1/oauth2/token_info',
    headers={'Authorization': f'Bearer {token}'}
)

print(response.status_code)
print(response.text)
"
```

---

### 步骤 2: 测试不同 API 版本

eBay 有多个 API 版本，尝试不同的：

**Inventory API v1.1:**
```
/commerce/inventory/v1_1/inventory_item
```

**Sell API v1.7:**
```
/sell/inventory/v1_7/offer
```

---

## 📊 测试结果记录

### 测试 1: GetAccount (Trading API)
```
✓ 成功 - 卖家账号已激活
```

### 测试 2: Get Offers (Sell API)
```
❌ 403 Forbidden - 权限不足
```

### 测试 3: Get Inventory Items
```
⚠️ 404 Not Found - 可能是空的
```

---

## 🎯 建议下一步

### 立即可做：
1. **使用 Trading API** - 既然可用，先用它发布测试 Listing
2. **重新获取 User Token** - 确保授权所有权限

### 等待后做：
1. 等待 30-60 分钟后重新测试 Sell API
2. 如果仍然失败，联系 eBay 开发者支持

---

## 📞 eBay 开发者支持

如果问题持续，联系：
- 论坛：https://developer.ebay.com/community
- 文档：https://developer.ebay.com/docs

---

## 📝 临时方案

既然 Trading API 可用，可以：

1. 使用 Trading API 发布 Listing
2. 同时等待 Sell API 权限同步
3. 同步完成后切换到 Sell API（更现代化）

---

**需要我帮你：**
1. 创建 Trading API 发布脚本？
2. 重新获取 User Token 后再次测试？
3. 联系 eBay 支持？
