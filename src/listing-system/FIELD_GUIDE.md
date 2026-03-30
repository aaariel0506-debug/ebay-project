# eBay Listing 字段完整指南

本文档列出所有支持的字段，包括必填/可选说明、默认值、配置位置。

---

## 📋 字段总览

| 字段 | 英文名 | 必填 | 默认值 | 配置位置 | 说明 |
|------|--------|------|--------|----------|------|
| **基本信息** |
| SKU | `sku` | ✅ 必填 | - | Excel / 代码 | 唯一商品标识 |
| 标题 | `title` | ✅ 必填 | - | Excel / 预审核页 | 最多 80 字符 |
| 副标题 | `subtitle` | ❌ 可选 | 空 | 预审核页 | 付费功能 |
| 分类 ID | `category_id` | ✅ 必填 | - | Excel / 代码 | eBay 分类 ID |
| 描述 | `description` | ✅ 必填 | - | Excel / 预审核页 | HTML 格式 |
| **价格与库存** |
| 价格 | `price` | ✅ 必填 | - | Excel / 预审核页 | USD 金额 |
| 库存数量 | `quantity` | ✅ 必填 | - | Excel / 预审核页 | 可售数量 |
| 数量折扣 | `quantity_discount` | ❌ 可选 | `[]` | 预审核页 | JSON 格式 |
| **商品属性** |
| 品牌 | `brand` | ⚠️ 推荐 | - | Excel / 预审核页 | 品牌名称 |
| 型号 | `model` | ❌ 可选 | - | Excel / 预审核页 | 产品型号 |
| MPN | `mpn` | ❌ 可选 | - | Excel / 预审核页 | 制造商编号 |
| UPC | `upc` | ❌ 可选 | - | Excel / 预审核页 | 条形码 |
| EAN | `ean` | ❌ 可选 | - | 代码 | 欧洲条形码 |
| ISBN | `isbn` | ❌ 可选 | - | 代码 | 图书 ISBN |
| 颜色 | `color` | ❌ 可选 | - | Excel / 预审核页 | 颜色名称 |
| 尺寸 | `size` | ❌ 可选 | - | Excel / 预审核页 | 尺寸规格 |
| 材质 | `material` | ❌ 可选 | - | Excel / 预审核页 | 材质名称 |
| 产地 | `country_of_manufacture` | ❌ 可选 | - | Excel / 预审核页 | 生产国家 |
| 类型 | `item_type` | ❌ 可选 | - | Excel / 预审核页 | 商品类型 |
| 系列 | `series` | ❌ 可选 | - | Excel / 预审核页 | 产品系列 |
| **图片** |
| 图片 URL | `image_urls` | ⚠️ 推荐 | - | Excel / 预审核页 | 逗号分隔，最多 12 张 |
| 运费说明图 | `shipping_info_image` | ❌ 可选 | 自动添加 | config.json | 默认运费说明图片 |
| **物流设置** |
| 处理时间 | `handling_time` | ❌ 可选 | `2` | config.json / 预审核页 | 天数 |
| 配送地区 | `ship_to_locations` | ❌ 可选 | `US,CA,GB,AU` | config.json / 预审核页 | 逗号分隔 |
| 排除地区 | `exclude_ship_to_locations` | ❌ 可选 | 空 | config.json / 预审核页 | 逗号分隔 |
| 促销运费 | `promotional_shipping` | ❌ 可选 | 配置值 | config.json / 预审核页 | 满额免运费 |
| **业务策略** |
| 付款政策 ID | `payment_policy_id` | ⚠️ 推荐 | config | config.json | 预配置政策 |
| 物流政策 ID | `fulfillment_policy_id` | ⚠️ 推荐 | config | config.json | 预配置政策 |
| 退货政策 ID | `return_policy_id` | ⚠️ 推荐 | config | config.json | 预配置政策 |
| 仓库位置 | `merchant_location_key` | ❌ 可选 | config | config.json | 仓库标识 |

---

## 📝 详细说明

### 1. 基本信息

#### SKU (`sku`)
- **必填**：✅
- **格式**：字母数字组合，不含特殊字符
- **示例**：`HOBO-2026-BLUE`, `SKU001`
- **说明**：唯一商品标识，用于库存追踪

#### 标题 (`title`)
- **必填**：✅
- **限制**：最多 80 字符
- **建议**：重点关键词放在前 56 字符（移动端显示）
- **示例**：`Hobonichi 5-Year Techo Gift Edition 2026-2030 haconiwa`

#### 副标题 (`subtitle`)
- **必填**：❌ 可选（付费功能）
- **限制**：最多 80 字符
- **费用**：约 $0.50/Listing
- **示例**：`Limited Edition - Free Shipping from Japan`
- **建议**：初期可不用，节省费用

#### 分类 ID (`category_id`)
- **必填**：✅
- **格式**：数字字符串
- **常用分类**：
  - `11450` - Books（沙盒测试用）
  - `1220` - Stationery & Office Supplies
  - `1221` - Paper Calendars & Planners
  - `1` - Collectibles

#### 描述 (`description`)
- **必填**：✅
- **格式**：HTML
- **说明**：支持 `<b>`, `<p>`, `<ul>`, `<li>`, `<img>` 等标签
- **示例**：
```html
<h2>Hobonichi 5-Year Techo Gift Edition</h2>
<p>Premium 5-year planner with beautiful design.</p>
<ul>
  <li>5-Year Planning (2026-2030)</li>
  <li>Premium Tomoe River paper</li>
  <li>Ships from Japan</li>
</ul>
```

---

### 2. 价格与库存

#### 价格 (`price`)
- **必填**：✅
- **格式**：数字（USD）
- **示例**：`50.00`, `189.99`

#### 库存数量 (`quantity`)
- **必填**：✅
- **格式**：整数
- **示例**：`10`, `100`

#### 数量折扣 (`quantity_discount`)
- **必填**：❌ 可选
- **格式**：JSON 数组
- **示例**：
```json
[
  {"quantity": 2, "discount_percent": 10},
  {"quantity": 5, "discount_percent": 15},
  {"quantity": 10, "discount_percent": 20}
]
```
- **说明**：买 2 件 9 折，买 5 件 85 折，买 10 件 8 折

---

### 3. 商品属性（Aspects）

#### 品牌 (`brand`)
- **必填**：⚠️ 推荐（部分分类必填）
- **示例**：`Hobonichi`, `Moleskine`, `Leuchtturm1917`

#### 型号 (`model`)
- **必填**：❌ 可选
- **示例**：`S2610`, `ABC-123`

#### MPN (`mpn`)
- **必填**：❌ 可选
- **说明**：Manufacturer Part Number
- **示例**：`HOBO-5YR-GIFT-2026`

#### UPC (`upc`)
- **必填**：❌ 可选（部分分类必填）
- **格式**：12 位数字
- **示例**：`123456789012`

#### 颜色 (`color`)
- **必填**：❌ 可选
- **示例**：`Blue`, `Black`, `Red`, `Navy`

#### 尺寸 (`size`)
- **必填**：❌ 可选
- **示例**：`A6`, `Large`, `One Size`

#### 材质 (`material`)
- **必填**：❌ 可选
- **示例**：`Paper`, `Leather`, `Cotton`, `Plastic`

#### 产地 (`country_of_manufacture`)
- **必填**：❌ 可选
- **格式**：国家名称
- **示例**：`Japan`, `China`, `United States`

#### 类型 (`item_type`)
- **必填**：❌ 可选
- **示例**：`Planner`, `Notebook`, `Journal`

#### 系列 (`series`)
- **必填**：❌ 可选
- **示例**：`Techo`, `Moleskine Classic`, `Leuchtturm Master`

---

### 4. 图片

#### 图片 URL (`image_urls`)
- **必填**：⚠️ 推荐（至少 1 张）
- **格式**：逗号分隔的 URL 列表
- **数量**：最多 12 张（1 主图 + 11 附图）
- **要求**：
  - 最小 500px，推荐 1600px+
  - 最大 7MB/张
  - 格式：JPEG, PNG, TIFF, BMP, GIF
- **示例**：
```
https://i.ebayimg.com/image1.jpg,https://i.ebayimg.com/image2.jpg
```

#### 运费说明图 (`shipping_info_image`)
- **必填**：❌ 可选（推荐添加）
- **默认**：自动添加到图片列表第 2 位
- **文件位置**：`templates/shipping_info.png`
- **说明**：展示运费政策、配送时效等信息

---

### 5. 物流设置

#### 处理时间 (`handling_time`)
- **必填**：❌ 可选
- **默认**：`2` 天
- **范围**：0-30 天
- **说明**：收到订单后发货所需工作日

#### 配送地区 (`ship_to_locations`)
- **必填**：❌ 可选
- **默认**：`US,CA,GB,AU`
- **格式**：逗号分隔的国家代码
- **常用代码**：
  - `US` - 美国
  - `CA` - 加拿大
  - `GB` - 英国
  - `AU` - 澳大利亚
  - `JP` - 日本
  - `DE` - 德国
  - `FR` - 法国

#### 排除地区 (`exclude_ship_to_locations`)
- **必填**：❌ 可选
- **默认**：空
- **格式**：逗号分隔的国家代码
- **示例**：`RU,BY`（排除俄罗斯、白俄罗斯）

#### 促销运费 (`promotional_shipping`)
- **必填**：❌ 可选
- **默认**：满 $50 免运费
- **格式**：JSON 对象
- **示例**：
```json
{"threshold": 50, "discount_percent": 100}
```
- **说明**：订单满 $50 免运费（100% 折扣）

---

### 6. 业务策略（预配置）

这些策略在 `config.json` 中预配置，自动应用到所有 Listing。

#### 付款政策 ID (`payment_policy_id`)
- **必填**：⚠️ 推荐
- **说明**：预配置的付款政策
- **获取方式**：在 eBay Seller Hub 创建后复制 ID

#### 物流政策 ID (`fulfillment_policy_id`)
- **必填**：⚠️ 推荐
- **说明**：预配置的物流政策（运费、承运商等）
- **获取方式**：在 eBay Seller Hub 创建后复制 ID

#### 退货政策 ID (`return_policy_id`)
- **必填**：⚠️ 推荐
- **说明**：预配置的退货政策
- **获取方式**：在 eBay Seller Hub 创建后复制 ID

#### 仓库位置 (`merchant_location_key`)
- **必填**：❌ 可选
- **说明**：库存位置标识
- **示例**：`TOKYO_WAREHOUSE_01`

---

## ⚙️ 配置文件示例 (config.json)

```json
{
  "environment": "sandbox",
  
  "sandbox": {
    "api_base": "https://api.sandbox.ebay.com",
    "web_base": "https://www.sandbox.ebay.com",
    "app_id": "YOUR_SANDBOX_APP_ID",
    "app_secret": "YOUR_SANDBOX_APP_SECRET",
    "cert_id": "YOUR_SANDBOX_CERT_ID"
  },
  
  "oauth": {
    "user_token": "YOUR_USER_TOKEN",
    "refresh_token": "YOUR_REFRESH_TOKEN",
    "scopes": [
      "https://api.ebay.com/oauth/api_scope",
      "https://api.ebay.com/oauth/api_scope/sell.inventory",
      "https://api.ebay.com/oauth/api_scope/sell.fulfillment"
    ]
  },
  
  "marketplace": {
    "marketplace_id": "EBAY_US",
    "currency": "USD",
    "locale": "en_US"
  },
  
  "business_policies": {
    "payment_policy_id": "PAYMENT_POLICY_ID_HERE",
    "fulfillment_policy_id": "FULFILLMENT_POLICY_ID_HERE",
    "return_policy_id": "RETURN_POLICY_ID_HERE"
  },
  
  "merchant_location_key": "TOKYO_WAREHOUSE_01",
  
  "listing_defaults": {
    "handling_time": 2,
    "ship_to_locations": ["US", "CA", "GB", "AU"],
    "exclude_ship_to_locations": [],
    "promotional_shipping": {
      "threshold": 50,
      "discount_percent": 100
    },
    "auto_publish": false,
    "format": "FIXED_PRICE",
    "condition": "NEW",
    "condition_id": "1000"
  },
  
  "image_upload": {
    "max_size_mb": 7,
    "recommended_dimension": 1600,
    "jpeg_quality": 90,
    "max_retries": 3,
    "default_images": [
      "templates/shipping_info.png"
    ]
  },
  
  "workflow": {
    "require_review": true
  }
}
```

---

## 📊 Excel 模板示例

| sku | title | price | quantity | category_id | brand | color | size | image_urls | quantity_discount |
|-----|-------|-------|----------|-------------|-------|-------|------|------------|-------------------|
| HOBO-001 | Hobonichi Techo 2026 | 50.00 | 10 | 1221 | Hobonichi | Blue | A6 | https://xxx.com/img1.jpg | `[{"quantity":2,"discount_percent":10}]` |
| HOBO-002 | Hobonichi 5-Year Techo | 189.00 | 5 | 1221 | Hobonichi | Multi | A6 | https://xxx.com/img2.jpg | `[]` |

---

## 🔧 下一步行动

### 需要完善的策略：

1. **业务政策**（在 eBay Seller Hub 创建）：
   - [ ] 付款政策 → 获取 `payment_policy_id`
   - [ ] 物流政策 → 获取 `fulfillment_policy_id`
   - [ ] 退货政策 → 获取 `return_policy_id`

2. **运费说明图片**：
   - [ ] 将图片保存到 `templates/shipping_info.png`
   - [ ] 在 config.json 中配置 `default_images`

3. **默认配置**（在 config.json 中设置）：
   - [ ] `handling_time` - 处理时间
   - [ ] `ship_to_locations` - 配送地区
   - [ ] `promotional_shipping` - 促销运费策略

4. **商品数据**（在 Excel 中完善）：
   - [ ] 品牌、型号、MPN
   - [ ] 颜色、尺寸、材质
   - [ ] 产地、类型、系列

---

## 📞 常用链接

- [eBay 分类浏览器](https://www.ebay.com/lhp/Navigation)
- [eBay 政策要求](https://www.ebay.com/help/policies)
- [eBay 图片要求](https://www.ebay.com/help/selling/listings/picture-requirements)
- [eBay 业务政策](https://www.ebay.com/help/selling/listings/business-policies)
