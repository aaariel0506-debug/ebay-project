# 🌐 eBay 沙盒网页验证步骤

**目标：** 通过网页手动创建 Listing，验证沙盒卖家账号权限正常

**预计时间：** 5-10 分钟

---

## 步骤 1：获取沙盒账号信息

1. 访问：https://developer.ebay.com/my/keys
2. 选择 **Sandbox** 环境
3. 查看并记录卖家账号：

```
Seller Account:
  Username: sbmc-stxxxxxx-seller
  Password: （点击显示）
```

---

## 步骤 2：登录沙盒 eBay

1. 访问：https://www.sandbox.ebay.com/signin
2. 使用沙盒卖家账号登录
3. 确认登录成功（看到 "Hi, xxxxx"）

---

## 步骤 3：手动创建 Listing

### 3.1 点击 "Sell" 按钮
```
页面顶部 → "Sell" → 开始创建 Listing
```

### 3.2 填写产品信息

| 字段 | 填写内容 |
|------|----------|
| **Title** | Hobonichi 5-Year Techo Gift Edition 2026-2030 |
| **Category** | Books & Magazines → Textbooks, Education & Reference |
| **Condition** | New |
| **Price** | $10.00 |
| **Quantity** | 1 |
| **Description** | Test listing for API verification |

### 3.3 填写配送信息
- **Shipping**: USPS First Class ($3.99)
- **Returns**: No returns accepted

### 3.4 提交 Listing
点击 "List item" 或 "Submit"

---

## 步骤 4：验证成功

### 成功标志
- ✅ 看到 "Your listing is live" 或类似提示
- ✅ 获得 Listing ID（如 123456789012）
- ✅ 可以在 "My eBay → Selling" 看到该 Listing

### 查看 Listing
访问：https://www.sandbox.ebay.com/s/my/ebay/selling

---

## 步骤 5：确认 API 权限

网页创建成功后，API 权限应该也正常了。

运行测试脚本验证：

```bash
cd /Users/arielhe/.openclaw/workspace/scripts
python3 ebay_publish_v3.py
```

如果还是无法获取 Offer ID，说明是沙盒环境的 API 限制（不是权限问题）。

---

## 📋 检查清单

完成后确认：

- [ ] 成功登录沙盒 eBay
- [ ] 网页手动创建 Listing 成功
- [ ] 看到 Listing ID
- [ ] 在 "Selling" 页面能看到该 Listing

---

## ⚠️ 常见问题

### Q: 登录后看不到 "Sell" 按钮？
A: 沙盒账号可能需要等待几分钟同步权限，刷新页面或重新登录。

### Q: 创建 Listing 时提示错误？
A: 检查：
- 类别是否选择叶子类别（最底层）
- 价格格式是否正确（如 10.00）
- 必填字段是否完整

### Q: 网页成功但 API 还是不行？
A: 这是 eBay 沙盒的已知限制。网页验证成功后，建议切换到生产环境。

---

## 下一步

网页验证成功后：

1. ✅ 确认沙盒账号权限正常
2. 🔄 考虑切换到生产环境（API 更稳定）
3. 📝 准备 5 款产品的完整发布流程

---

**验证完成后告诉我结果！** 🚀
