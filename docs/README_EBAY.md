# eBay Listing Generator - 自动化上架工具

## 功能

自动完成 eBay 商品上架流程：
1. 📥 抓取产品页面信息（任意 URL）
2. 🤖 调用 AI 生成 SEO 标题 + HTML 描述
3. 📤 通过 eBay API 发布 listing

## 快速开始

### 1. 获取 eBay API 密钥

1. 访问 [eBay Developers Program](https://developer.ebay.com/)
2. 注册账号并创建应用
3. 获取 **App ID (Client ID)** 和 **App Secret (Client Secret)**
4. 选择 **Sandbox 环境** 进行测试（生产环境需额外配置）

### 2. 配置脚本

```bash
cd /Users/arielhe/.openclaw/workspace/scripts

# 复制配置模板
cp ebay_config.example.json ebay_config.json

# 编辑配置文件，填入你的 API 密钥
nano ebay_config.json
```

### 3. 运行脚本

```bash
# 基本用法
python3 ebay_listing_generator.py <产品 URL> [价格] [分类 ID]

# 示例
python3 ebay_listing_generator.py https://www.1101.com/store/techo/en/2026/pc/detail_cover/fb26_s_haconiwa/ 39.99 1220
```

## 分类 ID 参考

| 分类 | ID |
|------|-----|
| Stationery & Office Supplies | 1220 |
| Paper Calendars & Planners | 1221 |
| Notebooks & Writing Pads | 1222 |
| Collectibles | 1 |

完整分类列表：https://www.ebay.com/help/policies/selling-policies/item-specifics-categories

## 与 OpenClaw 集成

脚本支持通过 OpenClaw 调用 AI 生成内容。在 `ebay_listing_generator.py` 中：

```python
# 方式 1：使用 OpenClaw sessions_spawn（推荐）
from openclaw import sessions_spawn

def generate_listing_openclaw(product_info: str):
    result = sessions_spawn(
        task=f"根据以下产品信息生成 eBay listing:\n{product_info}",
        runtime="subagent",
        mode="run"
    )
    # 解析返回的 title 和 description
    return title, description
```

## 环境变量（可选）

```bash
export EBAY_APP_ID="your_app_id"
export EBAY_APP_SECRET="your_app_secret"
```

## 注意事项

1. **Sandbox vs Production**
   - 默认使用 Sandbox 环境测试
   - 生产环境需修改 `EBAY_API_BASE` 为 `https://api.ebay.com`

2. **API 限制**
   - 免费账号：每日 5,000 次调用
   - 商业账号：更高限额

3. **Listing 审核**
   - 新账号的 listing 可能需要审核
   - 确保描述符合 eBay 政策

4. **图片上传**
   - 当前版本不支持自动上传图片
   - 需手动在 eBay 后台添加或使用 Picture API

## 扩展功能

### 批量上架

```python
# 创建批量脚本
products = [
    {"url": "https://...", "price": 29.99},
    {"url": "https://...", "price": 39.99},
]

for product in products:
    generate_and_publish(product["url"], product["price"])
```

### 定时任务

```bash
# 添加到 crontab
crontab -e

# 每天上午 10 点运行
0 10 * * * cd /Users/arielhe/.openclaw/workspace/scripts && python3 ebay_listing_generator.py <url> 29.99
```

## 故障排除

### 问题：获取 Token 失败
- 检查 App ID 和 Secret 是否正确
- 确认 eBay 开发者账号状态正常

### 问题：Listing 发布失败
- 检查分类 ID 是否有效
- 确认价格格式正确（USD）
- 查看 eBay API 返回的错误信息

### 问题：AI 生成内容为空
- 配置 AI API 密钥
- 或使用 OpenClaw 集成方式

## 联系支持

如有问题，请联系 Jarvis 或查看 eBay API 文档：
https://developer.ebay.com/docs
