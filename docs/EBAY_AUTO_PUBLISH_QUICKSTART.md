# 🚀 eBay 自动发布 - 快速开始指南

## 前置条件

- ✅ eBay 开发者账号（免费）
- ✅ 沙盒环境配置（测试用）
- ✅ Python 3.8+
- ✅ 产品 Listing 内容（已准备好 5 款 HTML）

---

## 步骤 1：注册 eBay 开发者账号（5 分钟）

### 1.1 访问开发者门户
```
https://developer.ebay.com/
```

### 1.2 创建账号
- 点击 "Sign In" → "Create an account"
- 填写邮箱、姓名、公司（个人即可）
- 验证邮箱

### 1.3 创建应用
```
Dashboard → Keys & Credentials → Production → Create a new key
- App Name: eBay Listing Tool
- 选择 "User Token"
- 点击 Create
```

### 1.4 保存密钥
创建成功后会显示：
- **App ID (Client ID)** ← 复制
- **Cert ID (Client Secret)** ← 复制
- **Dev ID** ← 复制（可选）

---

## 步骤 2：配置沙盒环境（3 分钟）

### 2.1 编辑配置文件
```bash
cd /Users/arielhe/.openclaw/workspace/scripts
nano ebay_config.json
```

### 2.2 填写密钥
```json
{
  "EBAY_APP_ID": "你的 App ID",
  "EBAY_APP_SECRET": "你的 Cert ID",
  "EBAY_DEV_ID": "你的 Dev ID",
  "EBAY_SITE_ID": "0",
  "EBAY_MARKETPLACE_ID": "EBAY_US",
  "EBAY_ENVIRONMENT": "sandbox"
}
```

### 2.3 保存退出
- `Ctrl+O` 保存
- `Enter` 确认
- `Ctrl+X` 退出

---

## 步骤 3：运行测试（2 分钟）

### 3.1 测试 API 连接
```bash
cd /Users/arielhe/.openclaw/workspace/scripts
python3 test_ebay_sandbox.py
```

### 3.2 预期输出
```
🧪 使用沙盒环境
📡 请求 OAuth Token...
✓ Token 获取成功
  Token: AQgABBB...xyz123
  
📦 测试 Inventory API...
✓ Inventory API 连接成功

🏪 测试 Sell API...
✓ Sell API 连接成功

🧪 创建测试 Listing...
  步骤 1: 创建 Inventory Item...
  ✓ Inventory Item 创建成功
  步骤 2: 创建 Offer...
  ✓ Offer 创建成功：v1^123456789
  步骤 3: 发布 Listing...
  ✓ Listing 发布成功！

🎉 测试完成！
  查看 Listing: https://www.sandbox.ebay.com/itm/v1^123456789
```

---

## 步骤 4：发布真实产品

### 4.1 使用自动发布脚本
```bash
python3 ebay_listing_auto.py <产品 URL> <价格> [分类 ID]

# 示例 - 发布 Hobonichi 5-Year haconiwa
python3 ebay_listing_auto.py \
  https://www.1101.com/store/techo/en/2026/pc/detail_cover/fb26_s_haconiwa/ \
  189.00 \
  1220
```

### 4.2 输出结果
```
🛒 eBay Listing Generator - Automated
============================================================
📥 抓取产品页面：https://...
✓ 抓取成功，内容长度：8061 字符
🤖 调用 OpenClaw AI 生成 listing...
✓ AI 生成成功
📤 发布 listing...
✓ Listing 创建成功！
Item ID: 123456789012
```

### 4.3 查看 Listing
- 沙盒：https://www.sandbox.ebay.com/itm/{ItemID}
- 生产：https://www.ebay.com/itm/{ItemID}

---

## 步骤 5：切换到生产环境（测试完成后）

### 5.1 修改配置
```bash
nano ebay_config.json
```

### 5.2 更改环境
```json
{
  "EBAY_ENVIRONMENT": "production",  // 改为 production
  ...
}
```

### 5.3 获取生产环境 Token
```
https://developer.ebay.com/tools/explorer
→ 选择 "Get User Token"
→ 选择环境：Production
→ 登录真实 eBay 卖家账号
→ 复制 Token 到配置文件的 OAUTH_TOKEN 字段
```

---

## 文件说明

| 文件 | 用途 |
|------|------|
| `ebay_config.json` | API 配置文件 |
| `ebay_config.example.json` | 配置模板 |
| `test_ebay_sandbox.py` | 沙盒测试脚本 |
| `ebay_listing_auto.py` | 自动发布脚本 |
| `ebay_sandbox_setup.md` | 详细设置指南 |
| `listings/*.html` | 产品 Listing 内容 |

---

## 常见问题

### Q: 测试需要多长时间？
A: 首次设置约 15 分钟（注册 + 配置），后续发布每个 Listing 约 2 分钟。

### Q: 沙盒测试收费吗？
A: 完全免费，沙盒环境不产生任何费用。

### Q: 可以同时测试多个 Listing 吗？
A: 可以，脚本会自动生成唯一 SKU。

### Q: 测试完成后如何删除沙盒 Listing？
A: 登录沙盒 eBay → My eBay → Selling → 删除

### Q: API 调用有限制吗？
A: 沙盒环境：每日 5,000 次；生产环境：根据账号等级。

---

## 下一步

1. ✅ 完成 eBay 开发者账号注册
2. ✅ 配置 `ebay_config.json`
3. ✅ 运行 `python3 test_ebay_sandbox.py`
4. ✅ 测试发布 Listing
5. 📊 查看结果并优化

---

## 需要帮助？

- 详细设置指南：`ebay_sandbox_setup.md`
- Listing 内容：`../listings/`
- 产品分析：`../reports/high_ticket_product_analysis_20260311.md`

**测试成功后，就可以开始批量发布 5 款产品了！** 🎉
