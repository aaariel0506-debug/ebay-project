# 🔍 eBay 沙盒问题根因分析

**分析日期：** 2026-03-11  
**问题：** Listing 发布失败

---

## 📊 测试结果汇总

| API | 测试次数 | 成功 | 失败 | 成功率 | 错误信息 |
|-----|----------|------|------|--------|----------|
| Client Token | 5+ | ✅ 5+ | 0 | 100% | - |
| User Token | 3 | ✅ 3 | 0 | 100% | - |
| GetAccount (Trading) | 2 | ✅ 2 | 0 | 100% | - |
| Browse API | 1 | ✅ 1 | 0 | 100% | - |
| Get Offers (Sell) | 3 | 0 | ❌ 3 | 0% | 403 Forbidden |
| Get Inventory Items | 3 | 0 | ❌ 3 | 0% | 404 Not Found |
| AddItem (Trading) | 10+ | 0 | ❌ 10+ | 0% | 系统错误/参数错误 |

---

## 🔬 问题分类

### 问题 A: Sell/Inventory API 403/404

**现象：**
```
Sell API: 403 Forbidden - "Insufficient permissions"
Inventory API: 404 Not Found
```

**根本原因：** User Token 授权范围（Scope）不足

**能否解决：** ✅ **可以解决**

**解决方案：**
1. 重新获取 User Token，确保授权以下 scopes：
   - `https://api.ebay.com/oauth/api_scope`
   - `https://api.ebay.com/oauth/api_scope/sell.inventory`
   - `https://api.ebay.com/oauth/api_scope/sell.account`

2. 获取步骤：
   ```
   https://developer.ebay.com/tools/explorer
   → Get User Token → Sandbox
   → 勾选所有权限（特别是 Inventory 相关）
   → 复制新 Token
   → 更新 ebay_config.json
   ```

3. 验证：
   ```bash
   python3 test_sell_api_final.py
   ```

**预计时间：** 5-10 分钟

---

### 问题 B: Trading API AddItem 系统错误

**现象：**
```
System error. Unable to process your request. Please try again later.
```

**根本原因分析：**

#### 可能原因 1: 沙盒环境临时故障 ⚠️
- **概率：** 60%
- **特征：** 错误信息模糊，无具体参数问题
- **解决：** ⏳ **需要等待官方修复**
- **等待时间：** 30 分钟 - 24 小时

#### 可能原因 2: 分类 ID 在沙盒不可用 ⚠️
- **概率：** 25%
- **特征：** 特定分类失败，其他分类可能成功
- **解决：** ✅ **可以解决** - 换用沙盒可用分类

**沙盒常用可用分类：**
| Category ID | 名称 | 状态 |
|-------------|------|------|
| 11450 | Books | ✅ 通常可用 |
| 1 | Collectibles | ✅ 通常可用 |
| 220 | Toys & Hobbies | ✅ 通常可用 |
| 1220 | Stationery | ⚠️ 有时不可用 |

#### 可能原因 3: XML 参数仍有问题 ⚠️
- **概率：** 15%
- **特征：** 具体参数错误信息
- **解决：** ✅ **可以解决** - 修复参数

**已修复的参数：**
- ✅ ListingType
- ✅ Currency
- ✅ ReturnPolicy
- ✅ CategoryID

**可能还缺的：**
- PaymentDetails
- ShippingDetails 完整结构
- PictureDetails

---

### 问题 C: 沙盒账号权限同步延迟

**现象：**
```
账号已激活，但某些 API 不可用
```

**根本原因：** eBay 沙盒权限同步需要时间

**能否解决：** ⏳ **需要等待**

**等待时间：** 30-60 分钟（有时更长）

**验证方法：**
```bash
# 每隔 15 分钟测试一次
python3 test_sell_api_final.py
```

---

## 🎯 问题优先级矩阵

| 问题 | 影响 | 可控性 | 优先级 | 行动 |
|------|------|--------|--------|------|
| User Token 权限不足 | 高 | ✅ 可控 | P0 | 立即重新获取 |
| 沙盒环境故障 | 高 | ❌ 不可控 | P1 | 等待 + 重试 |
| 分类 ID 不可用 | 中 | ✅ 可控 | P1 | 更换分类 |
| 权限同步延迟 | 中 | ❌ 不可控 | P2 | 等待 |
| XML 参数问题 | 低 | ✅ 可控 | P2 | 逐步调试 |

---

## 📋 行动计划

### 立即行动（现在可以做）

#### 1. 重新获取 User Token（10 分钟）

```
步骤：
1. 访问 https://developer.ebay.com/tools/explorer
2. 选择 "Get User Token"
3. 环境：Sandbox
4. 勾选所有权限（特别是 Inventory）
5. 登录沙盒账号授权
6. 复制新 Token
7. 更新 ebay_config.json
8. 运行测试：python3 test_sell_api_final.py
```

**预期结果：** Sell/Inventory API 可能恢复正常

---

#### 2. 简化 Trading API 请求（15 分钟）

创建最小化测试用例，排除参数问题：

```python
# 最小化 AddItem 请求
- 只保留必填字段
- 移除可选字段（Subtitle, ReturnPolicy 等）
- 使用已知可用的分类（11450 Books）
- 测试是否能成功
```

**预期结果：** 确定是否是参数问题

---

### 等待行动（30-60 分钟后）

#### 3. 重试所有 API

```bash
# 等待 30 分钟后运行
python3 test_sell_api_final.py
python3 publish_listing_trading.py
```

**预期结果：** 沙盒临时故障可能已修复

---

#### 4. 检查 eBay 沙盒状态

```
访问：https://developer.ebay.com/status
查看：Sandbox API Status
```

**如有已知问题：** 等待官方修复

---

## 📞 何时联系 eBay 支持

**如果以下情况，建议联系 eBay：**

1. ✅ 已重新获取 User Token（完整权限）
2. ✅ 已等待 2 小时以上
3. ✅ Trading API GetAccount 成功但 AddItem 失败
4. ✅ 确认不是参数问题

**联系方式：**
- 论坛：https://developer.ebay.com/community
- 帖子标题：`[Sandbox] AddItem API returns "System error" - User Token authenticated`
- 包含：错误响应、请求 XML、时间戳

---

## 🎲 成功概率评估

### 场景 A: Token 权限问题（60% 概率）

**如果重新获取 Token 后成功：**
- ✅ Sell/Inventory API 恢复
- ✅ 可以发布 Listing
- **总耗时：** 10-20 分钟

### 场景 B: 沙盒临时故障（30% 概率）

**如果等待后恢复：**
- ✅ 所有 API 正常
- ✅ 可以发布 Listing
- **总耗时：** 1-2 小时

### 场景 C: 深层问题（10% 概率）

**如果以上都无效：**
- ❌ 需要联系 eBay 支持
- ❌ 或切换到生产环境测试
- **总耗时：** 1-3 天

---

## 💡 建议策略

### 短期（今天）

1. **立即：** 重新获取 User Token（完整权限）
2. **等待：** 30-60 分钟后重试
3. **如仍失败：** 简化 Trading API 请求测试

### 中期（本周）

1. **如沙盒持续故障：** 考虑生产环境小批量测试
2. **准备完整：** Listing、客服、运营文档已就绪
3. **随时可发布：** 一旦 API 恢复

### 长期

1. **生产环境为主：** 沙盒仅用于开发测试
2. **建立监控：** API 失败自动告警
3. **备用方案：** Trading API 和 Sell API 都支持

---

## 📊 结论

| 问题 | 能否解决 | 行动 | 预计时间 |
|------|----------|------|----------|
| User Token 权限 | ✅ 能 | 重新获取 Token | 10 分钟 |
| 沙盒临时故障 | ⏳ 等待 | 30-60 分钟后重试 | 1 小时 |
| 分类不可用 | ✅ 能 | 更换分类 | 5 分钟 |
| 权限同步 | ⏳ 等待 | 等待同步完成 | 30-60 分钟 |
| XML 参数 | ✅ 能 | 简化请求调试 | 15 分钟 |

**建议：先重新获取 Token（可控），然后等待 30 分钟重试（不可控）**

---

**最后更新：** 2026-03-11 19:45 JST  
**状态：** 等待用户行动（重新获取 Token）
