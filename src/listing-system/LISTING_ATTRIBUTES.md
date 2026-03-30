# eBay Listing 属性完整清单

> 用于 Listing 属性自动生成工具的配置参考
> 更新时间：2026-03-23

---

## 📋 属性总表（按优先级）

### 🔴 第一优先级：必填字段（无默认值）

| 字段名 | API 字段 | 类型 | 示例 | 说明 | 自动生成建议 |
|--------|---------|------|------|------|-------------|
| SKU | `sku` | string | `HOBO-2026-BL` | 唯一商品标识 | 品牌 + 年份 + 型号 + 颜色缩写 |
| 标题 | `title` | string | `Hobonichi 5-Year Techo 2026-2030` | 最多 80 字符 | 品牌 + 系列 + 年份 + 核心卖点 |
| 分类 ID | `category_id` | string | `1221` | eBay 分类 ID | 根据商品类型映射 |
| 价格 | `price` | number | `50.00` | USD 金额 | 成本价 × 利润率 |
| 库存数量 | `quantity` | integer | `10` | 可售数量 | 读取库存系统或手动设置 |
| 描述 | `description` | string (HTML) | `<p>...</p>` | HTML 描述 | 使用 HTML 模板生成 |

---

### 🟡 第二优先级：推荐字段（有默认值）

| 字段名 | API 字段 | 类型 | 默认值 | 示例 | 说明 | 自动生成建议 |
|--------|---------|------|--------|------|------|-------------|
| 品牌 | `brand` | string | - | `Hobonichi` | 品牌名称 | 从商品数据读取 |
| 条件 | `condition` | enum | `NEW` | `NEW`, `USED` | 商品状态 | 默认 NEW |
| 图片 URLs | `image_urls` | array | - | `["url1", "url2"]` | 最多 12 张 | 从商品图库读取 |
| 付款政策 ID | `payment_policy_id` | string | config | `265656298018` | 预配置 | 从 config 读取 |
| 物流政策 ID | `fulfillment_policy_id` | string | config | `266026679018` | 预配置 | 从 config 读取 |
| 退货政策 ID | `return_policy_id` | string | config | `265656303018` | 预配置 | 从 config 读取 |
| 仓库位置 | `merchant_location_key` | string | config | `us-portland` | 发货仓库 | 从 config 读取 |

---

### 🟢 第三优先级：可选字段（增强信息）

| 字段名 | API 字段 | 类型 | 默认值 | 示例 | 说明 | 自动生成建议 |
|--------|---------|------|--------|------|------|-------------|
| 型号 | `model` | string | - | `S2610` | 产品型号 | 从商品数据读取 |
| MPN | `mpn` | string | - | `HOBO-5YR-2026` | 制造商编号 | 品牌 + 系列 + 年份 |
| UPC | `upc` | string | - | `123456789012` | 条形码 | 从商品数据读取 |
| 颜色 | `color` | string | - | `Blue` | 颜色名称 | 从商品数据读取 |
| 尺寸 | `size` | string | - | `A6` | 尺寸规格 | 从商品数据读取 |
| 材质 | `material` | string | - | `Paper` | 材质名称 | 从商品数据读取 |
| 产地 | `country_of_manufacture` | string | - | `Japan` | 生产国家 | 从商品数据读取 |
| 类型 | `item_type` | string | - | `Planner` | 商品类型 | 从分类映射 |
| 系列 | `series` | string | - | `Techo` | 产品系列 | 从商品数据读取 |
| 副标题 | `subtitle` | string | - | `Limited Edition` | 付费功能 | 可选，节省费用 |
| EAN | `ean` | string | - | `1234567890123` | 欧洲条形码 | 欧洲站点需要 |
| ISBN | `isbn` | string | - | `978-4-123456-78-9` | 图书 ISBN | 图书类商品 |

---

### 🔵 第四优先级：物流与营销配置

| 字段名 | API 字段 | 类型 | 默认值 | 示例 | 说明 | 自动生成建议 |
|--------|---------|------|--------|------|------|-------------|
| 处理时间 | `handling_time` | integer | `2` | `2` | 发货工作日 | 从 config 读取 |
| 配送地区 | `ship_to_locations` | array | `["US","CA","GB","AU"]` | `["US","JP"]` | 国家代码列表 | 从 config 读取 |
| 排除地区 | `exclude_ship_to_locations` | array | `[]` | `["RU","BY"]` | 不配送地区 | 从 config 读取 |
| 数量折扣 | `quantity_discount` | array | `[]` | 见下方 | 批量折扣 | 根据策略生成 |
| 促销运费 | `promotional_shipping` | object | 满$50 免运费 | 见下方 | 满额包邮 | 从 config 读取 |

---

## 📝 字段详细说明

### 一、基本信息

#### 1. SKU (`sku`)
```yaml
必填：是
类型：string (字母数字)
长度：1-50 字符
规则：不能包含特殊字符 (!@#$%^&*等)
示例：HOBO-2026-BL, MOLE-CLASSIC-BK-L
自动生成：{BRAND}-{YEAR}-{MODEL}-{COLOR}
```

#### 2. 标题 (`title`)
```yaml
必填：是
类型：string
长度：1-80 字符
建议：前 56 字符包含核心关键词（移动端显示）
格式：品牌 + 系列 + 年份 + 核心卖点 + 规格
示例：Hobonichi 5-Year Techo Gift Edition 2026-2030 haconiwa
自动生成模板：
  - "{brand} {series} {year} {feature} {size}"
  - "{brand} {product_type} {model} {color} {pack_size}"
```

#### 3. 分类 ID (`category_id`)
```yaml
必填：是
类型：string (数字)
常用分类:
  文具类:
    - "1220": Stationery & Office Supplies
    - "1221": Paper Calendars & Planners
    - "1222": Notebooks & Writing Pads
  图书类:
    - "11450": Books (测试用)
    - "377": Antiquarian & Collectible Books
  收藏品:
    - "1": Collectibles
自动生成：根据商品类型映射表
```

#### 4. 描述 (`description`)
```yaml
必填：是
类型：string (HTML)
长度：最多 8000 字符
支持标签：<b>, <p>, <ul>, <ol>, <li>, <img>, <h1>-<h6>, <div>, <span>
不支持：<script>, <style>, <iframe>, 外部 CSS/JS
自动生成：使用 HTML 模板（见下方模板章节）
```

---

### 二、价格与库存

#### 5. 价格 (`price`)
```yaml
必填：是
类型：number (decimal)
货币：USD (固定)
范围：0.01 - 999999.99
精度：2 位小数
示例：50.00, 189.99
自动生成：
  - 成本价 × 利润率
  - 或从价格表读取
```

#### 6. 库存数量 (`quantity`)
```yaml
必填：是
类型：integer
范围：0 - 9999
示例：10, 100, 999
自动生成：
  - 读取库存系统
  - 或设置固定值（如 999 表示充足）
```

#### 7. 数量折扣 (`quantity_discount`)
```yaml
必填：否
类型：array of objects
格式：
  [
    {"quantity": 2, "discount_percent": 10},
    {"quantity": 5, "discount_percent": 15},
    {"quantity": 10, "discount_percent": 20}
  ]
说明：
  - quantity: 最低购买数量
  - discount_percent: 折扣百分比 (0-100)
自动生成：根据定价策略配置
默认策略：
  - 买 2 件 9 折
  - 买 5 件 85 折
  - 买 10 件 8 折
```

---

### 三、商品属性 (Aspects)

#### 8. 品牌 (`brand`)
```yaml
必填：推荐（部分分类必填）
类型：string
示例：Hobonichi, Moleskine, Leuchtturm1917, Midori
自动生成：从商品数据读取
```

#### 9. 型号 (`model`)
```yaml
必填：否
类型：string
示例：S2610, ABC-123, HB-5YR-2026
自动生成：从商品 SKU 或数据表读取
```

#### 10. MPN (`mpn`)
```yaml
必填：否
类型：string
说明：Manufacturer Part Number
示例：HOBO-5YR-GIFT-2026
自动生成：{BRAND}-{SERIES}-{YEAR}
```

#### 11. UPC (`upc`)
```yaml
必填：否（部分分类必填）
类型：string
格式：12 位数字
示例：123456789012
自动生成：从商品数据读取（如有）
```

#### 12. 颜色 (`color`)
```yaml
必填：否
类型：string
常用值：Black, White, Blue, Red, Green, Navy, Multi-Color
自动生成：从商品数据读取
```

#### 13. 尺寸 (`size`)
```yaml
必填：否
类型：string
常用值：A5, A6, B6, Large, Medium, Small, One Size
自动生成：从商品规格读取
```

#### 14. 材质 (`material`)
```yaml
必填：否
类型：string
常用值：Paper, Leather, Cotton, Plastic, Metal, Cloth
自动生成：从商品数据读取
```

#### 15. 产地 (`country_of_manufacture`)
```yaml
必填：否
类型：string
常用值：Japan, China, United States, Germany, France
自动生成：从商品数据读取
```

#### 16. 类型 (`item_type`)
```yaml
必填：否
类型：string
常用值：Planner, Notebook, Journal, Diary, Organizer
自动生成：根据分类映射
```

#### 17. 系列 (`series`)
```yaml
必填：否
类型：string
示例：Techo, Moleskine Classic, Leuchtturm Master, Midori MD
自动生成：从商品数据读取
```

---

### 四、图片

#### 18. 图片 URLs (`image_urls`)
```yaml
必填：推荐（至少 1 张）
类型：array of strings
数量：1-12 张
格式：["url1", "url2", "url3"]
要求：
  - 最小尺寸：500px
  - 推荐尺寸：1600px+ (支持 zoom)
  - 最大文件：7MB/张
  - 格式：JPEG, PNG, TIFF, BMP, GIF
自动生成：
  - 从商品图库读取
  - 自动添加运费说明图（第 2 位）
  - 最多保留 12 张
```

---

### 五、物流设置

#### 19. 处理时间 (`handling_time`)
```yaml
必填：否
类型：integer
范围：0-30 天
默认值：2
示例：2, 3, 5
自动生成：从 config.listing_defaults.handling_time 读取
```

#### 20. 配送地区 (`ship_to_locations`)
```yaml
必填：否
类型：array of strings
默认值：["US", "CA", "GB", "AU"]
国家代码：
  - US: 美国
  - CA: 加拿大
  - GB: 英国
  - AU: 澳大利亚
  - JP: 日本
  - DE: 德国
  - FR: 法国
  - IT: 意大利
  - ES: 西班牙
自动生成：从 config.listing_defaults.ship_to_locations 读取
```

#### 21. 排除地区 (`exclude_ship_to_locations`)
```yaml
必填：否
类型：array of strings
默认值：[]
示例：["RU", "BY"] (排除俄罗斯、白俄罗斯)
自动生成：从 config.listing_defaults.exclude_ship_to_locations 读取
```

#### 22. 促销运费 (`promotional_shipping`)
```yaml
必填：否
类型：object
格式：{"threshold": 50, "discount_percent": 100}
说明：
  - threshold: 订单金额门槛 (USD)
  - discount_percent: 运费折扣百分比 (100=免运费)
默认值：满$50 免运费
自动生成：从 config.listing_defaults.promotional_shipping 读取
```

---

## 🎨 HTML 描述模板

### 基础模板
```html
<!DOCTYPE html>
<html>
<head>
  <meta charset="UTF-8">
  <style>
    body { font-family: Arial, sans-serif; line-height: 1.6; color: #333; }
    h1 { color: #2c5530; font-size: 24px; border-bottom: 2px solid #2c5530; padding-bottom: 10px; }
    h2 { color: #2c5530; font-size: 20px; margin-top: 20px; }
    .highlight { background: #f5f9f5; padding: 15px; border-left: 4px solid #2c5530; margin: 15px 0; }
    .features { background: #fafafa; padding: 15px; border-radius: 5px; }
    .features ul { margin: 10px 0; padding-left: 20px; }
    .features li { margin: 8px 0; }
    .shipping { background: #fff8e1; padding: 15px; border: 1px solid #ffe082; margin-top: 20px; }
    img { max-width: 100%; height: auto; }
  </style>
</head>
<body>
  <h1>{{title}}</h1>
  
  <div class="highlight">
    <strong>✨ {{highlight_text}}</strong>
  </div>
  
  <h2>Product Highlights</h2>
  <div class="features">
    <ul>
      {{#features}}
      <li>{{feature}}</li>
      {{/features}}
    </ul>
  </div>
  
  <h2>Specifications</h2>
  <table style="width: 100%; border-collapse: collapse;">
    {{#specs}}
    <tr>
      <td style="padding: 8px; border: 1px solid #ddd; background: #f9f9f9; width: 30%;"><strong>{{name}}</strong></td>
      <td style="padding: 8px; border: 1px solid #ddd;">{{value}}</td>
    </tr>
    {{/specs}}
  </table>
  
  <div class="shipping">
    <h2>Shipping Information</h2>
    <p><strong>Ships from:</strong> {{ship_from}}</p>
    <p><strong>Handling time:</strong> {{handling_time}} business days</p>
    <p><strong>Delivery time:</strong> {{delivery_time}}</p>
    {{#free_shipping}}
    <p style="color: #2c5530;"><strong>🎉 Free shipping on orders over $50!</strong></p>
    {{/free_shipping}}
  </div>
  
  <p style="margin-top: 30px; color: #666; font-size: 12px;">
    <em>Thank you for shopping with us! If you have any questions, please feel free to contact us.</em>
  </p>
</body>
</html>
```

### 模板变量说明
| 变量 | 说明 | 示例值 |
|------|------|--------|
| `{{title}}` | 商品标题 | Hobonichi 5-Year Techo |
| `{{highlight_text}}` | 亮点描述 | Special Limited Edition - Miniature garden themed |
| `{{features}}` | 特性列表 (array) | ["5-Year Planning", "Premium paper", ...] |
| `{{specs}}` | 规格表 (array of {name, value}) | [{name: "Brand", value: "Hobonichi"}, ...] |
| `{{ship_from}}` | 发货地 | Osaka, Japan |
| `{{handling_time}}` | 处理时间 | 2 |
| `{{delivery_time}}` | 配送时效 | 7-14 business days |
| `{{free_shipping}}` | 是否免运费 (boolean) | true |

---

## ⚙️ 配置文件参考 (config.json)

```json
{
  "listing_defaults": {
    "format": "FIXED_PRICE",
    "condition": "NEW",
    "condition_id": "1000",
    "handling_time": 2,
    "ship_to_locations": ["US", "CA", "GB", "AU", "JP"],
    "exclude_ship_to_locations": [],
    "promotional_shipping": {
      "threshold": 50,
      "discount_percent": 100
    },
    "quantity_discount": {
      "enabled": true,
      "tiers": [
        {"quantity": 2, "discount_percent": 10},
        {"quantity": 5, "discount_percent": 15},
        {"quantity": 10, "discount_percent": 20}
      ]
    },
    "auto_publish": false
  },
  
  "business_policies": {
    "payment_policy_id": "265656298018",
    "fulfillment_policy_id": "266026679018",
    "return_policy_id": "265656303018"
  },
  
  "merchant_location_key": "us-portland",
  
  "image_upload": {
    "max_size_mb": 7,
    "recommended_dimension": 1600,
    "jpeg_quality": 90,
    "max_retries": 3,
    "default_images": [
      "templates/shipping_info.png"
    ],
    "auto_add_shipping_info": true
  },
  
  "attribute_generation": {
    "sku_pattern": "{brand}-{year}-{model}-{color}",
    "title_pattern": "{brand} {series} {year} {feature} {size}",
    "mpn_pattern": "{brand}-{series}-{year}",
    "default_brand": "Hobonichi",
    "default_country": "Japan",
    "category_mapping": {
      "planner": "1221",
      "notebook": "1222",
      "stationery": "1220",
      "book": "11450"
    }
  }
}
```

---

## 🔧 自动生成工具开发建议

### 1. SKU 生成器
```python
def generate_sku(brand, year, model, color):
    """生成 SKU: HOBO-2026-S2610-BL"""
    brand_code = brand[:4].upper()  # HOBO
    color_code = color[:2].upper()  # BL
    return f"{brand_code}-{year}-{model}-{color_code}"
```

### 2. 标题生成器
```python
def generate_title(brand, series, year, feature, size):
    """生成标题，控制在 80 字符内"""
    title = f"{brand} {series} {year} {feature} {size}"
    if len(title) > 80:
        title = title[:77] + "..."
    return title
```

### 3. HTML 描述生成器
```python
def generate_description(template_vars):
    """使用模板生成 HTML 描述"""
    from jinja2 import Template
    with open('templates/listing_description.html', 'r') as f:
        template = Template(f.read())
    return template.render(**template_vars)
```

### 4. 属性映射器
```python
CATEGORY_MAPPING = {
    'planner': '1221',
    'notebook': '1222',
    'stationery': '1220',
    'book': '11450'
}

def get_category_id(product_type):
    return CATEGORY_MAPPING.get(product_type.lower(), '1220')
```

---

## 📊 数据验证规则

```python
VALIDATION_RULES = {
    'sku': {
        'required': True,
        'pattern': r'^[A-Z0-9\-]{1,50}$',
        'message': 'SKU 只能包含大写字母、数字和连字符'
    },
    'title': {
        'required': True,
        'max_length': 80,
        'message': '标题最多 80 字符'
    },
    'price': {
        'required': True,
        'min': 0.01,
        'max': 999999.99,
        'message': '价格范围 0.01-999999.99'
    },
    'quantity': {
        'required': True,
        'min': 0,
        'max': 9999,
        'type': 'integer',
        'message': '库存数量 0-9999'
    },
    'category_id': {
        'required': True,
        'pattern': r'^\d+$',
        'message': '分类 ID 必须是数字'
    },
    'brand': {
        'required': False,
        'recommended': True,
        'max_length': 70
    },
    'image_urls': {
        'required': False,
        'recommended': True,
        'max_items': 12,
        'url_pattern': r'^https?://'
    }
}
```

---

## 📞 常用链接

- [eBay 分类浏览器](https://www.ebay.com/lhp/Navigation)
- [eBay 属性要求](https://www.ebay.com/help/selling/listings/item-specifics)
- [eBay 图片要求](https://www.ebay.com/help/selling/listings/picture-requirements)
- [eBay HTML 指南](https://www.ebay.com/help/selling/listings/html-usage)
