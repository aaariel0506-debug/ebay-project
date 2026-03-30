# eBay Inventory API 完整属性清单

> 基于 eBay Inventory API 官方文档整理的完整字段列表
> 用于属性生成规则配置和数据验证
> 更新时间：2026-03-23

---

## 📋 API 端点总览

### 1. Inventory Item API
```
PUT /sell/inventory/v1/inventory_item/{SKU}
```
**用途：** 创建或更新库存商品

### 2. Offer API
```
POST /sell/inventory/v1/offer
GET  /sell/inventory/v1/offer?sku={SKU}
```
**用途：** 创建销售报价（Listing 草稿）

### 3. Publish API
```
POST /sell/inventory/v1/offer/{offerId}/publish
```
**用途：** 发布 Listing 到 eBay

---

## 🔴 Inventory Item API - 完整字段

### 请求体结构 (PUT /sell/inventory/v1/inventory_item/{SKU})

```json
{
  "sku": "string",
  "product": {
    "title": "string",
    "description": "string",
    "imageUrls": ["string"],
    "aspects": {
      "Brand": ["string"],
      "Model": ["string"],
      ...
    },
    "upc": ["string"],
    "ean": ["string"],
    "isbn": ["string"],
    "mpn": "string"
  },
  "condition": "string",
  "availability": {
    "shipToLocationAvailability": {
      "quantity": integer
    }
  },
  "packageWeightAndSize": {
    "dimensions": {
      "width": "string",
      "length": "string",
      "height": "string",
      "unit": "string"
    },
    "weight": {
      "value": "string",
      "unit": "string"
    }
  },
  "merchantLocationKey": "string"
}
```

---

### 字段详细说明

#### 1. SKU (`sku`)
```yaml
位置：根级别
类型：string
必填：是
长度：1-50 字符
规则：
  - 只能包含：字母 (a-z, A-Z)、数字 (0-9)、连字符 (-)
  - 不能包含：空格、特殊字符 (!@#$%^&*()_+=[]{}|;:',.<>?/\`)
  - 区分大小写（建议统一大写）
  - 在店铺内必须唯一
示例：HOBO-2026-S2610-BL, MOLE-CLASSIC-BK-L
用途：库存追踪、订单匹配、商品识别
```

#### 2. 产品标题 (`product.title`)
```yaml
位置：product.title
类型：string
必填：是
长度：1-80 字符
规则：
  - 不能包含 HTML 标签
  - 不能包含促销信息（如"Free Shipping"）
  - 不能包含价格信息
  - 建议前 56 字符包含核心关键词（移动端显示限制）
示例：Hobonichi 5-Year Techo Gift Edition 2026-2030 haconiwa
用途：商品标题（搜索结果显示）
```

#### 3. 产品描述 (`product.description`)
```yaml
位置：product.description
类型：string (HTML)
必填：否（推荐）
长度：最多 8000 字符
支持标签：
  - 文本：<b>, <i>, <u>, <s>, <em>, <strong>, <small>
  - 段落：<p>, <div>, <span>, <br>
  - 标题：<h1>, <h2>, <h3>, <h4>, <h5>, <h6>
  - 列表：<ul>, <ol>, <li>
  - 表格：<table>, <tr>, <td>, <th>, <thead>, <tbody>
  - 图片：<img> (src 必须是 HTTPS)
  - 链接：<a href="https://...">
不支持：
  - <script>, <style>, <iframe>, <object>, <embed>
  - 外部 CSS 文件引用
  - JavaScript
示例：
  <h2>Product Description</h2>
  <p>Premium quality planner from Japan.</p>
  <ul>
    <li>5-Year Planning (2026-2030)</li>
    <li>Tomoe River paper</li>
  </ul>
用途：商品详情描述（显示在 Listing 页面）
```

#### 4. 图片 URLs (`product.imageUrls`)
```yaml
位置：product.imageUrls
类型：array of strings
必填：否（强烈推荐）
数量：0-12 张
格式：["https://...", "https://..."]
要求：
  - 必须使用 HTTPS 协议
  - 最小尺寸：500px（任意一边）
  - 推荐尺寸：1600px+（支持 zoom 功能）
  - 最大文件：7MB/张
  - 支持格式：JPEG, PNG, TIFF, BMP, GIF
  - 第一张图作为主图（显示在搜索结果）
  - 不能包含水印、文字、边框
  - 不能使用占位图
示例：
  [
    "https://i.ebayimg.com/images/g/abcAAOSwXYtjkLm~/s-l1600.jpg",
    "https://i.ebayimg.com/images/g/defAAOSwYZtlkNp~/s-l1600.jpg"
  ]
用途：商品图片展示
```

#### 5. 商品属性 (`product.aspects`)
```yaml
位置：product.aspects
类型：object (key-value pairs)
必填：否（部分分类必填）
格式：{"属性名": ["值 1", "值 2"]}
说明：
  - 每个属性值必须是数组格式
  - 属性名和值区分大小写
  - 必须符合分类要求（不同分类有不同必填属性）
  - 属性名不能自定义，必须使用 eBay 预定义的
常用属性：
  - Brand: ["Hobonichi"]
  - Model: ["S2610"]
  - Color: ["Blue"]
  - Size: ["A6"]
  - Material: ["Paper"]
  - Type: ["Planner"]
  - Features: ["Limited Edition"]
  - Country/Region of Manufacture: ["Japan"]
  - Series: ["Techo"]
  - MPN: ["HOBO-5YR-2026"]
用途：商品规格参数（用于筛选和搜索）
```

#### 6. UPC (`product.upc`)
```yaml
位置：product.upc
类型：array of strings
必填：否（部分分类必填）
格式：["123456789012"]
规则：
  - 必须是 12 位数字
  - 必须是有效的 UPC-A 或 UPC-E 码
  - 部分分类强制要求（如电子产品）
示例：["123456789012"]
用途：商品条形码（北美标准）
```

#### 7. EAN (`product.ean`)
```yaml
位置：product.ean
类型：array of strings
必填：否（部分分类必填）
格式：["1234567890123"]
规则：
  - 必须是 13 位数字（EAN-13）或 8 位数字（EAN-8）
  - 必须是有效的 EAN 码
  - 欧洲站点强制要求
示例：["1234567890123"]
用途：商品条形码（欧洲标准）
```

#### 8. ISBN (`product.isbn`)
```yaml
位置：product.isbn
类型：array of strings
必填：否（图书类必填）
格式：["978-4-123456-78-9"] 或 ["9784123456789"]
规则：
  - 必须是 13 位（ISBN-13）或 10 位（ISBN-10）
  - 必须是有效的 ISBN 码
  - 图书类商品强制要求
示例：["9784123456789"]
用途：图书国际标准书号
```

#### 9. MPN (`product.mpn`)
```yaml
位置：product.mpn
类型：string
必填：否
长度：1-70 字符
规则：
  - 由制造商分配
  - 不能包含特殊字符
  - 建议格式：品牌缩写 - 系列 - 型号
示例：HOBO-5YR-GIFT-2026
用途：制造商零件编号
```

#### 10. 商品状态 (`condition`)
```yaml
位置：根级别
类型：string (enum)
必填：是
可选值：
  - NEW: 全新（未使用过）
  - USED: 二手（已使用过）
  - REFURBISHED: 翻新
  - LIKE_NEW: 几乎全新
默认值：NEW
示例：NEW
用途：商品新旧状态
```

#### 11. 库存数量 (`availability.shipToLocationAvailability.quantity`)
```yaml
位置：availability.shipToLocationAvailability.quantity
类型：integer
必填：是
范围：0-9999
规则：
  - 0 表示缺货
  - 9999 表示库存充足
  - 必须是非负整数
示例：10, 100, 999
用途：可售库存数量
```

#### 12. 包裹尺寸 (`packageWeightAndSize.dimensions`)
```yaml
位置：packageWeightAndSize.dimensions
类型：object
必填：否
字段：
  - width: string (数字字符串)
  - length: string (数字字符串)
  - height: string (数字字符串)
  - unit: string (CENTIMETER | INCH)
示例：
  {
    "width": "11.3",
    "length": "15.3",
    "height": "2.5",
    "unit": "CENTIMETER"
  }
用途：包裹尺寸（用于计算运费）
```

#### 13. 包裹重量 (`packageWeightAndSize.weight`)
```yaml
位置：packageWeightAndSize.weight
类型：object
必填：否
字段：
  - value: string (数字字符串)
  - unit: string (GRAM | KILOGRAM | OUNCE | POUND)
示例：
  {
    "value": "0.33",
    "unit": "KILOGRAM"
  }
用途：包裹重量（用于计算运费）
```

#### 14. 仓库位置 (`merchantLocationKey`)
```yaml
位置：根级别
类型：string
必填：否
规则：
  - 必须是在 eBay 注册的仓库
  - 通过 Location API 创建
  - 默认使用第一个创建的仓库
示例：us-portland, osaka-main
用途：指定库存所在位置
```

---

## 🟡 Offer API - 完整字段

### 请求体结构 (POST /sell/inventory/v1/offer)

```json
{
  "sku": "string",
  "marketplaceId": "string",
  "format": "string",
  "categoryId": "string",
  "listingDescription": "string",
  "merchantLocationKey": "string",
  "listingPolicies": {
    "paymentPolicyId": "string",
    "fulfillmentPolicyId": "string",
    "returnPolicyId": "string"
  },
  "pricingSummary": {
    "price": {
      "value": "string",
      "currency": "string"
    },
    "quantityDiscountPricing": {
      "quantityDiscountType": "string",
      "quantityDiscountTiers": [...]
    }
  },
  "availableQuantity": integer,
  "fulfillmentStartEndDate": {
    "handlingTime": {
      "value": integer,
      "unit": "string"
    },
    "shipToLocations": [...],
    "excludeShipToLocations": [...]
  },
  "promotionalShippingPolicies": [...],
  "title": "string"
}
```

---

### 字段详细说明

#### 1. SKU (`sku`)
```yaml
位置：根级别
类型：string
必填：是
规则：必须与 Inventory Item 的 SKU 一致
用途：关联库存商品
```

#### 2. 市场 ID (`marketplaceId`)
```yaml
位置：根级别
类型：string (enum)
必填：是
可选值：
  - EBAY_US: 美国站
  - EBAY_CA: 加拿大站
  - EBAY_GB: 英国站
  - EBAY_DE: 德国站
  - EBAY_FR: 法国站
  - EBAY_AU: 澳大利亚站
  - EBAY_JP: 日本站
默认值：EBAY_US
用途：指定上架的市场
```

#### 3. 销售格式 (`format`)
```yaml
位置：根级别
类型：string (enum)
必填：是
可选值：
  - FIXED_PRICE: 固定价格（立即购买）
  - AUCTION: 拍卖
默认值：FIXED_PRICE
用途：销售方式
```

#### 4. 分类 ID (`categoryId`)
```yaml
位置：根级别
类型：string (数字)
必填：是
规则：
  - 必须是 eBay 分类树中的有效 ID
  - 叶子分类（最底层分类）
  - 不同市场分类可能不同
常用分类：
  - "1220": Stationery & Office Supplies
  - "1221": Paper Calendars & Planners
  - "1222": Notebooks & Writing Pads
  - "11450": Books
  - "1": Collectibles
用途：商品分类
```

#### 5. Listing 描述 (`listingDescription`)
```yaml
位置：根级别
类型：string (HTML)
必填：否
长度：最多 8000 字符
规则：与 product.description 相同
用途：商品详情描述（会覆盖 product.description）
```

#### 6. 仓库位置 (`merchantLocationKey`)
```yaml
位置：根级别
类型：string
必填：是
规则：必须与 Inventory Item 中的仓库一致
用途：指定发货仓库
```

#### 7. 业务政策 (`listingPolicies`)
```yaml
位置：listingPolicies
类型：object
必填：是
字段：
  - paymentPolicyId: string (付款政策 ID)
  - fulfillmentPolicyId: string (物流政策 ID)
  - returnPolicyId: string (退货政策 ID)
说明：
  - 三个政策 ID 都必须提供
  - 必须在 eBay Seller Hub 预先创建
  - 政策 ID 是长数字字符串
示例：
  {
    "paymentPolicyId": "265656298018",
    "fulfillmentPolicyId": "266026679018",
    "returnPolicyId": "265656303018"
  }
用途：应用预配置的业务政策
```

#### 8. 定价摘要 (`pricingSummary`)
```yaml
位置：pricingSummary
类型：object
必填：是
字段：
  - price: {value: string, currency: string}
  - quantityDiscountPricing: object (可选)
说明：
  - value: 价格金额（字符串格式）
  - currency: 货币代码（USD, EUR, GBP 等）
示例：
  {
    "price": {
      "value": "50.00",
      "currency": "USD"
    }
  }
用途：商品定价
```

#### 9. 数量折扣 (`pricingSummary.quantityDiscountPricing`)
```yaml
位置：pricingSummary.quantityDiscountPricing
类型：object
必填：否
字段：
  - quantityDiscountType: string (VOLUME_PRICING)
  - quantityDiscountTiers: array
阶梯定义：
  - minimumQuantity: integer (最低购买数量)
  - price: {value: string, currency: string} (折扣后单价)
示例：
  {
    "quantityDiscountType": "VOLUME_PRICING",
    "quantityDiscountTiers": [
      {
        "minimumQuantity": 2,
        "price": {"value": "45.00", "currency": "USD"}
      },
      {
        "minimumQuantity": 5,
        "price": {"value": "42.50", "currency": "USD"}
      }
    ]
  }
用途：批量购买折扣
```

#### 10. 可售数量 (`availableQuantity`)
```yaml
位置：根级别
类型：integer
必填：是
范围：1-9999
规则：
  - 不能超过 Inventory Item 的库存
  - 0 表示不可售
示例：10, 100
用途：该 Offer 的可售数量
```

#### 11. 处理时间 (`fulfillmentStartEndDate.handlingTime`)
```yaml
位置：fulfillmentStartEndDate.handlingTime
类型：object
必填：否
字段：
  - value: integer (天数)
  - unit: string (固定为 DAY)
范围：0-30 天
默认值：2
示例：
  {
    "value": 2,
    "unit": "DAY"
  }
用途：订单处理时间（工作日）
```

#### 12. 配送地区 (`fulfillmentStartEndDate.shipToLocations`)
```yaml
位置：fulfillmentStartEndDate.shipToLocations
类型：array of objects
必填：否
格式：[{"regionCode": "US"}, {"regionCode": "CA"}]
常用代码：
  - US: 美国
  - CA: 加拿大
  - GB: 英国
  - AU: 澳大利亚
  - JP: 日本
  - DE: 德国
  - FR: 法国
  - IT: 意大利
  - ES: 西班牙
示例：
  [
    {"regionCode": "US"},
    {"regionCode": "CA"},
    {"regionCode": "GB"}
  ]
用途：指定配送到的国家/地区
```

#### 13. 排除地区 (`fulfillmentStartEndDate.excludeShipToLocations`)
```yaml
位置：fulfillmentStartEndDate.excludeShipToLocations
类型：array of objects
必填：否
格式：[{"regionCode": "RU"}, {"regionCode": "BY"}]
示例：
  [
    {"regionCode": "RU"},
    {"regionCode": "BY"}
  ]
用途：不配送的国家/地区
```

#### 14. 促销运费 (`promotionalShippingPolicies`)
```yaml
位置：promotionalShippingPolicies
类型：array
必填：否
字段：
  - minimumOrderAmount: {value: string, currency: string}
  - shippingDiscountPercent: integer (0-100)
示例：
  [
    {
      "minimumOrderAmount": {
        "value": "50",
        "currency": "USD"
      },
      "shippingDiscountPercent": 100
    }
  ]
说明：
  - minimumOrderAmount: 订单金额门槛
  - shippingDiscountPercent: 运费折扣（100=免运费）
用途：满额包邮促销
```

#### 15. 副标题 (`title`)
```yaml
位置：根级别
类型：string
必填：否
长度：1-80 字符
说明：
  - 这是副标题（Subtitle），不是主标题
  - 主标题在 Inventory Item 的 product.title
  - 副标题是付费功能（约$0.50/Listing）
  - 不是所有分类都支持
示例：Limited Edition - Free Shipping from Japan
用途：补充说明（显示在主标题下方）
```

---

## 📊 字段映射表（Inventory Item → Offer）

| Inventory Item 字段 | Offer 字段 | 说明 |
|---------------------|------------|------|
| `sku` | `sku` | 必须一致 |
| `product.title` | - | 主标题（不能覆盖） |
| `product.description` | `listingDescription` | Offer 可覆盖 |
| `product.imageUrls` | - | 继承，不能覆盖 |
| `condition` | - | 继承，不能覆盖 |
| `availability.quantity` | `availableQuantity` | Offer 不能超过 Inventory |
| `merchantLocationKey` | `merchantLocationKey` | 必须一致 |
| - | `marketplaceId` | Offer 独有 |
| - | `categoryId` | Offer 独有 |
| - | `listingPolicies` | Offer 独有 |
| - | `pricingSummary` | Offer 独有 |
| - | `fulfillmentStartEndDate` | Offer 独有 |

---

## 🔧 属性生成规则配置建议

### SKU 编码规则
```yaml
pattern: "{BRAND}-{YEAR}-{MODEL}-{COLOR}"
示例：
  - HOBO-2026-S2610-BL
  - MOLE-2025-CLASSIC-BK
  - LEUC-2026-MASTER-RD
字段说明：
  - BRAND: 品牌缩写（4 字母）
  - YEAR: 年份（4 数字）
  - MODEL: 型号代码（4-6 字符）
  - COLOR: 颜色缩写（2 字母）
规则：
  - 全部大写
  - 用连字符分隔
  - 总长度不超过 50 字符
```

### 标题生成规则
```yaml
pattern: "{brand} {series} {year} {feature} {size}"
最大长度：80 字符
优先级：
  1. 品牌 (brand)
  2. 系列 (series)
  3. 年份/型号 (year/model)
  4. 核心卖点 (feature)
  5. 规格 (size)
示例：
  - "Hobonichi 5-Year Techo Gift Edition 2026-2030 haconiwa"
  - "Moleskine Classic Notebook Large Ruled Black"
截断规则：
  - 超过 80 字符时，从后往前截断
  - 保留完整单词（不在单词中间截断）
  - 添加 "..." 表示截断
```

### 分类映射规则
```yaml
mapping:
  planner: "1221"        # Paper Calendars & Planners
  notebook: "1222"       # Notebooks & Writing Pads
  stationery: "1220"     # Stationery & Office Supplies
  book: "11450"          # Books
  collectible: "1"       # Collectibles
  journal: "1222"        # Notebooks & Writing Pads
  diary: "1221"          # Paper Calendars & Planners
  organizer: "1220"      # Stationery & Office Supplies
默认值：1220
```

### 颜色标准化映射
```yaml
mapping:
  # 黑色系
  black: "Black"
  bk: "Black"
  charcoal: "Charcoal"
  # 白色系
  white: "White"
  wh: "White"
  cream: "Cream"
  # 蓝色系
  blue: "Blue"
  bl: "Blue"
  navy: "Navy"
  royal: "Royal Blue"
  # 红色系
  red: "Red"
  rd: "Red"
  crimson: "Crimson"
  # 绿色系
  green: "Green"
  gr: "Green"
  forest: "Forest Green"
  # 多色
  multi: "Multi-Color"
  multicolor: "Multi-Color"
  rainbow: "Multi-Color"
规则：
  - 统一使用 eBay 标准颜色名
  - 不常见的颜色映射到最接近的标准色
  - 多色商品使用 "Multi-Color"
```

### 尺寸标准化映射
```yaml
mapping:
  # 手帐尺寸
  a6: "A6"
  a5: "A5"
  b6: "B6"
  # 笔记本尺寸
  small: "Small"
  medium: "Medium"
  large: "Large"
  pocket: "Pocket"
  # 通用
  one_size: "One Size"
  onesize: "One Size"
  standard: "Standard"
规则：
  - 统一使用大写
  - 手帐使用 ISO 标准（A6, A5, B6）
  - 笔记本使用 S/M/L
```

### 产地标准化映射
```yaml
mapping:
  japan: "Japan"
  jp: "Japan"
  china: "China"
  cn: "China"
  united_states: "United States"
  us: "United States"
  usa: "United States"
  germany: "Germany"
  de: "Germany"
  france: "France"
  fr: "France"
  italy: "Italy"
  it: "Italy"
  uk: "United Kingdom"
  gb: "United Kingdom"
  united_kingdom: "United Kingdom"
规则：
  - 使用完整国家名称
  - 不使用缩写（除 United States/United Kingdom）
```

---

## ✅ 数据验证清单

### 必填字段检查
- [ ] SKU（1-50 字符，字母数字连字符）
- [ ] 标题（1-80 字符）
- [ ] 分类 ID（有效数字）
- [ ] 价格（0.01-999999.99）
- [ ] 库存数量（0-9999 整数）
- [ ] 商品状态（NEW/USED/REFURBISHED/LIKE_NEW）
- [ ] 仓库位置（已注册）
- [ ] 业务政策 ID（3 个）
- [ ] 市场 ID（EBAY_US 等）
- [ ] 销售格式（FIXED_PRICE/AUCTION）

### 格式验证
- [ ] SKU 不含特殊字符
- [ ] 标题不含 HTML 标签
- [ ] 图片 URL 是 HTTPS
- [ ] 价格字符串格式（"50.00"）
- [ ] 尺寸单位（CENTIMETER/INCH）
- [ ] 重量单位（GRAM/KILOGRAM）
- [ ] 国家代码（2 字母大写）

### 业务规则
- [ ] Offer 数量 ≤ Inventory 数量
- [ ] 仓库位置一致
- [ ] 分类是叶子分类
- [ ] 图片至少 1 张（推荐）
- [ ] 品牌属性（部分分类必填）

---

## 📞 官方文档链接

- [Inventory API 参考](https://developer.ebay.com/api-docs/sell/inventory/resources)
- [Inventory Item 资源](https://developer.ebay.com/api-docs/sell/inventory/resources/inventory_item)
- [Offer 资源](https://developer.ebay.com/api-docs/sell/inventory/resources/offer)
- [分类树 API](https://developer.ebay.com/api-docs/commerce/taxonomy/resources)
- [业务政策](https://www.ebay.com/help/selling/listings/business-policies)
