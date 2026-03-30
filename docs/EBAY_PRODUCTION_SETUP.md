# 🌐 eBay 生产环境设置指南

**⚠️ 重要：** 生产环境与沙盒完全独立，需要单独配置！

---

## 步骤 1：获取生产环境 API 密钥

### 1.1 访问开发者门户
```
https://developer.ebay.com/
```

### 1.2 切换到 Production 环境
```
Dashboard → Keys & Credentials → 选择 "Production"
```

### 1.3 创建生产应用（如没有）
```
Create a new key
- App Name: eBay Listing Tool Production
- 选择 "User Token"
- 点击 Create
```

### 1.4 保存密钥
创建成功后会显示：
- **App ID (Client ID)** ← 复制
- **Cert ID (Client Secret)** ← 复制
- **Dev ID** ← 复制

⚠️ **重要：** Cert ID 只显示一次，立即保存！

---

## 步骤 2：获取生产环境 User Token

### 2.1 访问 Token 工具
```
https://developer.ebay.com/tools/explorer
```

### 2.2 选择 Production 环境
```
Environment: ● Production  ← 确保选这个！
```

### 2.3 获取 Token
```
1. 点击 "Get User Token"
2. 登录你的真实 eBay 卖家账号
3. 授权应用（勾选所有权限）
4. 复制生成的 Token
```

Token 格式示例：
```
v^1.1#i^1#r^1#f^0#I^3#p^3#t^H4sIAAAAAAAA...
(很长的字符串)
```

---

## 步骤 3：配置本地文件

### 3.1 创建生产环境配置

```bash
cd /Users/arielhe/.openclaw/workspace/scripts
cp ebay_config.json ebay_config_production.json
nano ebay_config_production.json
```

### 3.2 填写生产环境密钥

```json
{
  "_comment": "eBay API 配置文件 - 生产环境",
  
  "EBAY_APP_ID": "你的生产环境 App ID",
  "EBAY_APP_SECRET": "你的生产环境 Cert ID",
  "EBAY_DEV_ID": "你的生产环境 Dev ID",
  "EBAY_SITE_ID": "0",
  "EBAY_MARKETPLACE_ID": "EBAY_US",
  
  "EBAY_ENVIRONMENT": "production",
  
  "OAUTH_TOKEN": "你的生产环境 User Token"
}
```

### 3.3 保存退出
```
Ctrl+O → 保存
Enter → 确认
Ctrl+X → 退出
```

---

## 步骤 4：修改发布脚本

### 4.1 创建生产环境发布脚本

```bash
cp publish_listing_trading.py publish_listing_production.py
nano publish_listing_production.py
```

### 4.2 修改配置引用

找到这一行：
```python
CONFIG_FILE = SCRIPT_DIR / "ebay_config.json"
```

改为：
```python
CONFIG_FILE = SCRIPT_DIR / "ebay_config_production.json"
```

### 4.3 修改 API 端点

找到这一行：
```python
# API 端点会在配置中根据环境自动选择
```

确保 API 端点是：
```python
EBAY_PROD_API_BASE = "https://api.ebay.com"
EBAY_PROD_WS = "https://api.ebay.com/ws/api.dll"
```

---

## 步骤 5：测试生产环境

### 5.1 运行测试

```bash
cd /Users/arielhe/.openclaw/workspace/scripts
python3 publish_listing_production.py
```

### 5.2 预期输出

```
🧪 eBay Trading API - 发布测试 Listing
============================================================

User Token: v^1.1#i^1#r^1#f^0#I^3#p^3#t^...

📦 产品信息:
  标题：【TEST】Hobonichi Techo 2026 - Production Test
  价格：$0.99
  分类：11450
  数量：1

📡 发送 AddItem 请求...
响应状态码：200

✅ Listing 发布成功！

📦 Item ID: 123456789012
🔗 查看链接：https://www.ebay.com/itm/123456789012
```

---

## ⚠️ 重要注意事项

### 费用说明

| 项目 | 沙盒环境 | 生产环境 |
|------|----------|----------|
| **Listing 费** | 免费 | $0.30/个（部分分类免费） |
| **成交费** | 免费 | 13% 左右 |
| **支付处理费** | 免费 | 2.9% + $0.30 |
| **店铺费** | 免费 | $0-800/月（可选） |

### 测试建议

1. **先发布 1 个测试 Listing**
   - 价格设低（$0.99）
   - 标题注明【TEST】
   - 描述说明是测试

2. **确认可用后再发布真实产品**

3. **及时删除测试 Listing**
   - 登录 eBay → My eBay → Selling
   - 找到测试 Listing → End Item

### 安全提示

- 🔒 不要将 API 密钥上传到 GitHub
- 🔒 定期轮换 Cert ID
- 🔒 Token 有效期 18 个月，过期重新获取
- 🔒 生产环境谨慎操作，会产生真实费用

---

## 📋 生产环境 vs 沙盒环境

| 特性 | 沙盒 | 生产 |
|------|------|------|
| **网址** | sandbox.ebay.com | ebay.com |
| **API 端点** | api.sandbox.ebay.com | api.ebay.com |
| **费用** | 免费 | 正常收费 |
| **数据** | 测试数据 | 真实交易 |
| **买家** | 测试账号 | 真实买家 |
| **稳定性** | 可能不稳定 | 稳定 |
| **用途** | 开发测试 | 真实销售 |

---

## 🎯 快速切换环境

### 使用沙盒测试
```bash
python3 publish_listing_trading.py
```

### 使用生产环境
```bash
python3 publish_listing_production.py
```

---

## ❓ 常见问题

### Q: 生产环境 API 密钥和沙盒一样吗？
A: **不一样！** 需要分别获取。

### Q: 可以用沙盒 Token 访问生产环境吗？
A: **不可以！** 沙盒和生产完全隔离。

### Q: 生产环境测试会产生费用吗？
A: 会，但很少：
- Listing 费：$0（前 250 个/月通常免费）
- 成交费：只有卖出才收取

### Q: 如何避免测试 Listing 被真实购买？
A: 
1. 标题注明【TEST】
2. 描述说明是测试
3. 价格设异常（$0.99 或 $999）
4. 测试完立即删除

### Q: 生产环境不稳定怎么办？
A: 生产环境通常很稳定，如遇到问题：
1. 检查 API 密钥是否正确
2. 检查 Token 是否过期
3. 查看 eBay API 状态：https://developer.ebay.com/status

---

## 📞 需要帮助？

- 开发者文档：https://developer.ebay.com/docs
- API 状态：https://developer.ebay.com/status
- 社区论坛：https://developer.ebay.com/community

---

**准备好后，告诉我你的生产环境 API 密钥，我帮你配置！**
