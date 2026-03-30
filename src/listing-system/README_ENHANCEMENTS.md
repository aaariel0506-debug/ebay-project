# eBay Listing 功能增强说明

本文档说明新增的三大功能模块。

---

## 🖼️ 1. 图片上传功能

**文件：** `ebay_image_uploader.py`

### 功能特性

- ✅ 本地图片上传到 eBay 图片托管
- ✅ 自动压缩（超过 7MB 时）
- ✅ 格式转换（统一为 JPEG）
- ✅ 批量上传
- ✅ 上传进度显示
- ✅ 错误重试机制

### eBay 图片要求

| 项目 | 要求 |
|------|------|
| 格式 | JPEG, PNG, TIFF, BMP, GIF |
| 大小 | 最大 7MB/张 |
| 尺寸 | 最小 500px，推荐 1600px+（支持 zoom） |
| 数量 | 最多 12 张（1 主图 + 11 附图） |

### 使用方法

#### 命令行使用

```bash
# 上传单张图片
python3 ebay_image_uploader.py product_image.jpg

# 上传多张图片
python3 ebay_image_uploader.py image1.jpg image2.jpg image3.jpg

# 上传整个文件夹
python3 ebay_image_uploader.py ./product_images/

# 从 URL 上传
python3 ebay_image_uploader.py https://example.com/image.jpg
```

#### 代码集成

```python
from ebay_client import EbayClient
from ebay_image_uploader import EbayImageUploader

# 初始化
client = EbayClient()
uploader = EbayImageUploader(client)

# 上传单张
result = uploader.upload_local_image("./product.jpg")
if result.success:
    print(f"图片 URL: {result.picture_url}")

# 批量上传
results = uploader.upload_batch(["img1.jpg", "img2.jpg", "img3.jpg"])
picture_urls = [r.picture_url for r in results if r.success]

# 上传文件夹
results = uploader.upload_from_folder("./product_images/", pattern="*.jpg")
```

#### 集成到 Listing 创建

```python
# 1. 先上传图片
uploader = EbayImageUploader(client)
results = uploader.upload_from_folder("./product_images/")
picture_urls = [r.picture_url for r in results if r.success]

# 2. 将图片 URL 填入商品数据
item_data = {
    "sku": "SKU001",
    "title": "Product Title",
    "image_urls": ",".join(picture_urls),  # 逗号分隔
    # ... 其他字段
}

# 3. 创建 Listing
creator = ListingCreatorEnhanced(client)
result = creator.create_listing(item_data)
```

---

## 📦 2. 订单同步功能

**文件：** `order_sync.py`

### 功能特性

- ✅ 获取订单列表（按时间范围/状态过滤）
- ✅ 获取订单详情
- ✅ 标记发货（上传物流单号）
- ✅ 订单数据本地存储（Excel/JSON）
- ✅ 增量同步（基于上次同步时间）
- ✅ 自动通知买家

### 支持的订单状态

| 状态 | 说明 |
|------|------|
| UNPAID | 未付款 |
| PAID | 已付款 |
| SHIPPED | 已发货 |
| CANCELLED | 已取消 |
| REFUNDED | 已退款 |

### 使用方法

#### 命令行使用

```bash
# 同步最近 30 天订单
python3 order_sync.py sync

# 同步最近 7 天订单
python3 order_sync.py sync --days 7

# 查看订单详情
python3 order_sync.py detail <order_id>

# 标记发货（日本邮政）
python3 order_sync.py ship <order_id> JAPAN_POST <tracking_number>

# 标记发货（任意承运商）
python3 order_sync.py ship <order_id> FEDEX 123456789

# 查看同步状态
python3 order_sync.py status
```

#### 代码集成

```python
from ebay_client import EbayClient
from order_sync import OrderSync

# 初始化
client = EbayClient()
sync = OrderSync(client)

# 获取订单列表
orders = sync.get_orders(
    start_date="2026-03-01T00:00:00Z",
    end_date="2026-03-18T23:59:59Z",
    status="PAID",
    limit=100
)

# 保存订单
sync.save_orders_to_excel(orders)  # Excel 格式
sync.save_orders_to_json(orders)   # JSON 格式

# 获取订单详情
order = sync.get_order_detail("12345-67890-12345")
print(f"买家：{order.buyer_username}")
print(f"商品：{len(order.line_items)} 件")

# 标记发货
success = sync.mark_shipped_japan_post(
    order_id="12345-67890-12345",
    tracking_number="EJ123456789JP"
)

# 查看同步状态
status = sync.get_sync_status()
print(f"上次同步：{status['last_sync_time']}")
print(f"累计订单：{status['total_orders_synced']}")
```

#### 定时同步（Cron 示例）

```bash
# 每天凌晨 2 点同步前一天的订单
0 2 * * * cd /path/to/ebay_automation && python3 order_sync.py sync --days 1
```

---

## 📝 3. 商品属性增强

**文件：** `listing_creator_enhanced.py`

### 新增字段支持

#### Inventory Item 层级

| 字段 | 说明 | 示例 |
|------|------|------|
| `color` | 颜色 | "Red", "Blue", "Black" |
| `size` | 尺寸 | "M", "L", "One Size" |
| `material` | 材质 | "Cotton", "Leather", "Paper" |
| `model` | 型号 | "ABC-123" |
| `country_of_manufacture` | 产地 | "Japan", "China", "US" |
| `item_type` | 类型 | "Planner", "Notebook" |
| `series` | 系列 | "Techo", "Moleskine" |
| `ean` | EAN 码（欧洲） | "1234567890123" |
| `isbn` | ISBN 码（图书） | "978-4-123456-78-9" |

#### Offer 层级

| 字段 | 说明 | 示例 |
|------|------|------|
| `subtitle` | 副标题（付费） | "Limited Edition Gift Set" |
| `quantity_discount` | 数量折扣 | `[{quantity: 2, discount_percent: 10}]` |
| `handling_time` | 处理时间（天） | `2` |
| `ship_to_locations` | 配送地区 | `["US", "CA", "GB", "AU"]` |
| `exclude_ship_to_locations` | 排除地区 | `["RU", "BY"]` |
| `promotional_shipping` | 促销运费 | `{threshold: 50, discount_percent: 100}` |

### 使用方法

#### Excel 字段示例

| sku | title | price | color | size | material | quantity_discount |
|-----|-------|-------|-------|------|----------|-------------------|
| SKU001 | Hobonichi Techo | 50.00 | Blue | A6 | Paper | `[{"quantity": 2, "discount_percent": 10}]` |
| SKU002 | Moleskine Notebook | 30.00 | Black | Large | Leather | |

#### 代码示例

```python
from ebay_client import EbayClient
from listing_creator_enhanced import ListingCreatorEnhanced

client = EbayClient()
creator = ListingCreatorEnhanced(client)

item_data = {
    "sku": "HOBO-2026-BLUE",
    "title": "Hobonichi Techo 2026",
    "description": "<p>Premium planner...</p>",
    "price": 50.00,
    "category_id": "11450",
    
    # 新增字段
    "color": "Blue",
    "size": "A6",
    "material": "Paper",
    "model": "S2610",
    "country_of_manufacture": "Japan",
    "brand": "Hobonichi",
    
    # 数量折扣
    "quantity_discount": [
        {"quantity": 2, "discount_percent": 10},
        {"quantity": 5, "discount_percent": 15}
    ],
    
    # 处理时间
    "handling_time": 2,
    
    # 配送地区
    "ship_to_locations": ["US", "CA", "GB", "AU", "JP"],
    
    # 排除地区
    "exclude_ship_to_locations": ["RU", "BY"],
    
    # 促销运费（满$50 免运费）
    "promotional_shipping": {"threshold": 50, "discount_percent": 100},
    
    # 图片（可先用图片上传工具获取 URL）
    "image_urls": "https://i.ebayimg.com/xxx,https://i.ebayimg.com/yyy",
}

result = creator.create_listing(item_data, auto_publish=False)

if result.success:
    print(f"Listing 创建成功！")
    print(f"Offer ID: {result.offer_id}")
else:
    print(f"失败：{result.error}")
```

---

## 🔧 配置说明

### config.json 新增配置项

```json
{
  "image_upload": {
    "max_size_mb": 7,
    "recommended_dimension": 1600,
    "jpeg_quality": 90,
    "max_retries": 3
  },
  
  "order_sync": {
    "default_days": 30,
    "auto_save_excel": true,
    "auto_save_json": true
  },
  
  "listing_defaults": {
    "handling_time": 2,
    "ship_to_locations": ["US", "CA", "GB", "AU"],
    "promotional_shipping": {
      "threshold": 50,
      "discount_percent": 100
    }
  }
}
```

---

## 📌 依赖安装

```bash
# 图片处理（图片上传功能需要）
pip install Pillow --break-system-packages

# Excel 处理（订单同步需要）
pip install openpyxl --break-system-packages

# 数据处理
pip install pandas --break-system-packages
```

---

## ⚠️ 注意事项

### 图片上传
- 沙盒环境的图片上传可能受限，建议在生产环境测试
- 图片 URL 有有效期，建议定期更新
- 首图会作为主图显示，注意顺序

### 订单同步
- 需要 `https://api.ebay.com/oauth/api_scope/fulfillment` 权限
- 物流单号必须符合承运商格式
- 标记发货后会自动通知买家

### 商品属性
- 不同分类的必填属性不同，请参考 eBay 分类要求
- 副标题是付费功能，会产生额外费用
- 数量折扣最多支持 5 档

---

## 📞 问题排查

### 图片上传失败
1. 检查文件大小是否超过 7MB
2. 检查文件格式是否支持
3. 检查 Token 权限是否包含 `https://api.ebay.com/oauth/api_scope/sell.inventory`

### 订单同步失败
1. 检查是否有所需的 Fulfillment API 权限
2. 检查订单 ID 格式是否正确
3. 检查时间范围是否合理

### Listing 创建失败
1. 检查分类 ID 是否正确
2. 检查必填属性是否完整
3. 查看错误信息中的具体字段要求

---

## 📚 相关文档

- [eBay Inventory API 文档](https://developer.ebay.com/api-docs/sell/inventory/resources)
- [eBay Fulfillment API 文档](https://developer.ebay.com/api-docs/sell/fulfillment/resources)
- [eBay 图片要求](https://www.ebay.com/help/selling/listings/picture-requirements)
