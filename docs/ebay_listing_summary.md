# eBay Listing 系统总结文档

**生成时间**: 2026-03-17 10:06 JST  
**系统位置**: `/Users/arielhe/.openclaw/workspace/scripts/ebay_automation/`

---

## 一、API Listing 发布功能

### 核心文件
| 文件 | 功能 | 状态 |
|------|------|------|
| `listing_creator.py` | Listing 创建编排 | ✅ 完成 |
| `ebay_client.py` | eBay API 客户端 | ✅ 完成 |
| `data_validator.py` | 数据验证 | ✅ 完成 |
| `config.json` | 生产配置 | ✅ 已配置 |

### API 调用流程
```
商品数据 → InventoryItem API → Offer API → [可选] Publish API
```

### 已测试 API 端点
| 端点 | 状态 | 说明 |
|------|------|------|
| `/identity/v1/oauth2/token` | ✅ | OAuth Token 自动刷新 |
| `/sell/inventory/v1/inventory_item/{sku}` | ✅ | 创建/更新商品 |
| `/sell/inventory/v1/offer` | ✅ | 创建 Offer（草稿）|
| `/sell/inventory/v1/offer/{id}/publish` | ✅ | 发布商品 |

### 已创建的 Listing（草稿状态）
| SKU | Offer ID | 状态 |
|-----|----------|------|
| HOBO-5Y-2026 | 133150135011 | UNPUBLISHED |
| HOBO-WEEKS-2026 | 133150139011 | UNPUBLISHED |
| HOBO-DIARY-2026 | 133150410011 | UNPUBLISHED |
| HOBO-MARINE-2026 | 133150611011 | 发布失败（category_id 无效）|

### 关键配置
```json
{
  "environment": "production",
  "auto_publish": true,
  "marketplace_id": "EBAY_US",
  "default_category_id": "260",
  "listing_defaults": {
    "format": "FIXED_PRICE",
    "duration": "GTC"
  }
}
```

### 已知问题
1. **HOBO-MARINE-2026** 因 `category_id` 无效发布失败
2. Token 自动续期正常，Refresh Token 有效

---

## 二、eBay Listing 预审核页面

### 文件位置
| 文件 | 功能 | 最后修改 |
|------|------|----------|
| `review_web.py` | Flask Web 服务 | 2026-03-16 23:26 |
| `templates/review.html` | 预审核页面模板 | 2026-03-16 22:42 |

### 启动方式
```bash
cd /Users/arielhe/.openclaw/workspace/scripts/ebay_automation
python review_web.py --port 8080
```

访问地址: `http://127.0.0.1:8080`

### 页面功能
1. **展示未发布 Offer** - 自动拉取 UNPUBLISHED 状态的 listing
2. **编辑字段**:
   - SKU
   - 标题（80字符限制）
   - 价格（USD）
   - 库存数量
   - 品牌 / MPN
   - 描述（支持 HTML）
3. **操作按钮**:
   - **保存** - 仅更新 InventoryItem
   - **保存并发布** - 更新后调用 Publish API
   - **跳过** - 标记为已处理

### 当前测试数据
- 硬编码测试 Offer ID: `133181542011`
- 需要改为动态拉取所有 UNPUBLISHED offers

### 技术栈
- **后端**: Flask (Python)
- **前端**: 原生 HTML + CSS
- **API 客户端**: `ebay_client.py` (复用)

---

## 三、待办事项

### 高优先级
1. [ ] 修复 HOBO-MARINE-2026 的 category_id
2. [ ] 修改 review_web.py 动态拉取所有 UNPUBLISHED offers（而非硬编码）
3. [ ] 在 Seller Hub 手动发布 3 个有效草稿，或修正后自动发布

### 中优先级
4. [ ] 添加预审核页面的搜索/筛选功能
5. [ ] 添加批量操作（批量保存/批量发布）
6. [ ] 添加图片预览功能

### 低优先级
7. [ ] 添加操作日志记录
8. [ ] 添加撤销/回滚功能

---

## 四、快速开始

### 1. 创建新 Listing
```bash
cd /Users/arielhe/.openclaw/workspace/scripts/ebay_automation
python create_listing.py --file 商品数据.xlsx
```

### 2. 启动预审核页面
```bash
python review_web.py --port 8080
# 访问 http://127.0.0.1:8080
```

### 3. 查看草稿
- Seller Hub: https://www.bay.com/sh/lst/drafts
- 搜索关键词: `Hobonichi` 或 SKU `HOBO-`

---

## 五、相关链接

- **工作日志**: `memory/2026-03-16.md`
- **代码目录**: `/Users/arielhe/.openclaw/workspace/scripts/ebay_automation/`
- **日志目录**: `/Users/arielhe/.openclaw/workspace/scripts/ebay_automation/logs/`
