# eBay Listing 属性生成规则配置

> 完整的属性自动生成规则配置文档
> 用于 Listing 属性生成工具的配置和验证
> 更新时间：2026-03-23

---

## 📋 规则总览

| 规则类别 | 规则数 | 说明 |
|----------|--------|------|
| SKU 编码规则 | 1 | 品牌 + 年份 + 型号 + 颜色 |
| 标题生成规则 | 1 | 品牌 + 系列 + 年份 + 卖点 + 规格 |
| 分类映射规则 | 1 | 商品类型 → eBay 分类 ID |
| 颜色标准化 | 1 | 颜色名映射表 |
| 尺寸标准化 | 1 | 尺寸名映射表 |
| 产地标准化 | 1 | 国家名映射表 |
| 默认值配置 | 1 | 各字段默认值 |
| 验证规则 | 1 | 数据验证规则 |

---

## 🔴 规则 1：SKU 编码规则

### 编码格式
```
{BRAND_CODE}-{YEAR}-{MODEL_CODE}-{COLOR_CODE}
```

### 字段说明

| 字段 | 长度 | 规则 | 示例 |
|------|------|------|------|
| `BRAND_CODE` | 4 字符 | 品牌名前 4 字母，大写 | HOBO, MOLE, LEUC, MIDO |
| `YEAR` | 4 字符 | 4 位年份数字 | 2026, 2025, 2027 |
| `MODEL_CODE` | 4-6 字符 | 型号代码，大写数字 | S2610, CLASSIC, MASTER |
| `COLOR_CODE` | 2 字符 | 颜色前 2 字母，大写 | BL, BK, WH, RD |

### 品牌代码映射表

| 品牌全称 | 代码 | 示例 SKU |
|----------|------|----------|
| Hobonichi | HOBO | HOBO-2026-S2610-BL |
| Moleskine | MOLE | MOLE-2025-CLASSIC-BK |
| Leuchtturm1917 | LEUC | LEUC-2026-MASTER-RD |
| Midori | MIDO | MIDO-2026-MD-A5-BL |
| Life | LIFE | LIFE-2026-NOBLE-BK |
| Traveler's Company | TRAV | TRAV-2026-NC-BR |
| Kokuyo | KOKU | KOKU-2026-JIBU-BL |
| Tombow | TOMO | TOMO-2026-MONO-BK |

### 颜色代码映射表

| 颜色 | 代码 | 颜色 | 代码 |
|------|------|------|------|
| Black | BK | Navy | NV |
| White | WH | Red | RD |
| Blue | BL | Green | GR |
| Pink | PK | Yellow | YL |
| Purple | PP | Orange | OR |
| Brown | BR | Gray | GY |
| Multi-Color | MC | Clear | CL |
| Gold | GD | Silver | SV |

### 生成示例

```python
# 输入数据
{
    "brand": "Hobonichi",
    "year": 2026,
    "model": "S2610",
    "color": "Blue"
}

# 生成过程
BRAND_CODE = "HOBO"  # Hobonichi 前 4 字母
YEAR = "2026"        # 年份
MODEL_CODE = "S2610" # 型号
COLOR_CODE = "BL"    # Blue 前 2 字母

# 输出
SKU = "HOBO-2026-S2610-BL"
```

### 验证规则

```yaml
pattern: "^[A-Z]{4}-\\d{4}-[A-Z0-9]{4,6}-[A-Z]{2}$"
max_length: 50
allowed_chars: "A-Z, 0-9, -"
separator: "-"
case: "UPPER"
```

---

## 🟡 规则 2：标题生成规则

### 生成格式
```
{brand} {series} {year} {feature} {size}
```

### 字段说明

| 字段 | 优先级 | 最大长度 | 说明 |
|------|--------|----------|------|
| `brand` | 1 | 20 字符 | 品牌名称 |
| `series` | 2 | 20 字符 | 系列名称 |
| `year` | 3 | 10 字符 | 年份/版本 |
| `feature` | 4 | 20 字符 | 核心卖点 |
| `size` | 5 | 10 字符 | 规格尺寸 |

### 长度控制

```yaml
max_length: 80
mobile_display: 56  # 移动端显示前 56 字符
truncation:
  enabled: true
  marker: "..."
  preserve_word: true  # 不在单词中间截断
```

### 生成示例

#### 示例 1：Hobonichi Techo
```yaml
输入:
  brand: "Hobonichi"
  series: "5-Year Techo Gift Edition"
  year: "2026-2030"
  feature: "haconiwa"
  size: "A6"

生成过程:
  "Hobonichi 5-Year Techo Gift Edition 2026-2030 haconiwa A6"
  长度：68 字符 ✓

输出:
  title: "Hobonichi 5-Year Techo Gift Edition 2026-2030 haconiwa A6"
```

#### 示例 2：Moleskine Classic
```yaml
输入:
  brand: "Moleskine"
  series: "Classic Notebook"
  year: ""
  feature: "Ruled"
  size: "Large, Black"

生成过程:
  "Moleskine Classic Notebook Ruled Large Black"
  长度：46 字符 ✓

输出:
  title: "Moleskine Classic Notebook Ruled Large Black"
```

#### 示例 3：超长截断
```yaml
输入:
  brand: "Leuchtturm1917"
  series: "Master Slim Notebook"
  year: "Anniversary Edition Limited"
  feature: "Dotted Premium Paper"
  size: "A5, Black"

生成过程:
  原始："Leuchtturm1917 Master Slim Notebook Anniversary Edition Limited Dotted Premium Paper A5 Black"
  长度：103 字符 ✗ (超过 80)
  
  截断："Leuchtturm1917 Master Slim Notebook Anniversary Edition Limited Dotted..."
  长度：80 字符 ✓

输出:
  title: "Leuchtturm1917 Master Slim Notebook Anniversary Edition Limited Dotted..."
```

### 优先级规则

```yaml
# 如果超过 80 字符，按优先级保留
priority_order:
  - brand      # 最高优先级，必须保留
  - series     # 第二优先级
  - year       # 第三优先级
  - feature    # 第四优先级
  - size       # 最低优先级，先截断

# 移动端优化（前 56 字符）
mobile_optimization:
  # 确保前 56 字符包含核心信息
  must_include:
    - brand
    - series
  optional:
    - year
```

---

## 🟢 规则 3：分类映射规则

### 商品类型 → eBay 分类 ID

```yaml
mapping:
  # 文具类
  planner:
    category_id: "1221"
    category_name: "Paper Calendars & Planners"
    required_aspects:
      - Brand
      - Type
      - Size
  
  notebook:
    category_id: "1222"
    category_name: "Notebooks & Writing Pads"
    required_aspects:
      - Brand
      - Type
      - Size
  
  journal:
    category_id: "1222"
    category_name: "Notebooks & Writing Pads"
    required_aspects:
      - Brand
      - Type
  
  diary:
    category_id: "1221"
    category_name: "Paper Calendars & Planners"
    required_aspects:
      - Brand
      - Type
  
  stationery:
    category_id: "1220"
    category_name: "Stationery & Office Supplies"
    required_aspects:
      - Brand
      - Type
  
  organizer:
    category_id: "1220"
    category_name: "Stationery & Office Supplies"
    required_aspects:
      - Brand
      - Type
  
  # 图书类
  book:
    category_id: "11450"
    category_name: "Books"
    required_aspects:
      - Author
      - Format
    additional_fields:
      - isbn: required
  
  # 收藏品
  collectible:
    category_id: "1"
    category_name: "Collectibles"
    required_aspects:
      - Type
  
  # 默认
  default:
    category_id: "1220"
    category_name: "Stationery & Office Supplies"
    required_aspects:
      - Brand
```

### 使用示例

```python
# 输入商品类型
product_type = "planner"

# 查找映射
category = CATEGORY_MAPPING.get(product_type, CATEGORY_MAPPING["default"])

# 输出
{
    "category_id": "1221",
    "category_name": "Paper Calendars & Planners",
    "required_aspects": ["Brand", "Type", "Size"]
}
```

---

## 🔵 规则 4：颜色标准化映射

### 完整映射表

```yaml
# 黑色系
black: "Black"
bk: "Black"
charcoal: "Charcoal"
slate: "Slate"
onyx: "Onyx"
jet_black: "Black"

# 白色系
white: "White"
wh: "White"
cream: "Cream"
ivory: "Ivory"
off_white: "Cream"

# 蓝色系
blue: "Blue"
bl: "Blue"
navy: "Navy"
royal: "Royal Blue"
sky: "Sky Blue"
light_blue: "Light Blue"
dark_blue: "Dark Blue"
azure: "Azure"

# 红色系
red: "Red"
rd: "Red"
crimson: "Crimson"
scarlet: "Scarlet"
burgundy: "Burgundy"
maroon: "Maroon"
dark_red: "Dark Red"

# 绿色系
green: "Green"
gr: "Green"
forest: "Forest Green"
olive: "Olive"
mint: "Mint Green"
lime: "Lime"
dark_green: "Dark Green"
light_green: "Light Green"

# 黄色系
yellow: "Yellow"
yl: "Yellow"
gold: "Gold"
mustard: "Mustard"
lemon: "Lemon"

# 橙色系
orange: "Orange"
or: "Orange"
coral: "Coral"
peach: "Peach"

# 紫色系
purple: "Purple"
pp: "Purple"
violet: "Violet"
lavender: "Lavender"
plum: "Plum"

# 粉色系
pink: "Pink"
pk: "Pink"
rose: "Rose"
magenta: "Magenta"
fuchsia: "Fuchsia"

# 棕色系
brown: "Brown"
br: "Brown"
tan: "Tan"
beige: "Beige"
chocolate: "Chocolate"
coffee: "Coffee"

# 灰色系
gray: "Gray"
gy: "Gray"
grey: "Gray"
silver: "Silver"
sv: "Silver"
platinum: "Platinum"

# 多色
multi: "Multi-Color"
multicolor: "Multi-Color"
rainbow: "Multi-Color"
pattern: "Multi-Color"
mixed: "Multi-Color"

# 透明/其他
clear: "Clear"
cl: "Clear"
transparent: "Clear"
metallic: "Metallic"
neon: "Neon"
```

### 使用示例

```python
# 输入
input_color = "bk"

# 查找映射
standardized_color = COLOR_MAPPING.get(input_color.lower(), input_color.title())

# 输出
"Black"
```

### 验证规则

```yaml
allowed_values:
  - "Black"
  - "White"
  - "Blue"
  - "Red"
  - "Green"
  - "Yellow"
  - "Orange"
  - "Purple"
  - "Pink"
  - "Brown"
  - "Gray"
  - "Navy"
  - "Multi-Color"
  - "Clear"
  - "Silver"
  - "Gold"

case: "Title"  # 首字母大写
```

---

## 🟣 规则 5：尺寸标准化映射

### 完整映射表

```yaml
# 手帐尺寸（ISO 标准）
a6: "A6"
a5: "A5"
a4: "A4"
b6: "B6"
b5: "B5"
b4: "B4"

# 笔记本尺寸
pocket: "Pocket"
small: "Small"
medium: "Medium"
large: "Large"
extra_large: "Extra Large"

# 具体尺寸（厘米）
90x140: "90x140mm"
105x148: "A7"  # A7 = 105x148mm
130x210: "A6"  # A6 = 105x148mm (实际 Hobonichi A6 是 130x148mm)
148x210: "A5"  # A5 = 148x210mm
210x297: "A4"  # A4 = 210x297mm

# 英寸尺寸
3_5x5_5: "3.5\" x 5.5\""
5x8: "5\" x 8\""
8_5x11: "8.5\" x 11\""

# 通用尺寸
one_size: "One Size"
onesize: "One Size"
standard: "Standard"
regular: "Regular"
mini: "Mini"
compact: "Compact"
jumbo: "Jumbo"
```

### 使用示例

```python
# 输入
input_size = "a6"

# 查找映射
standardized_size = SIZE_MAPPING.get(input_size.lower(), input_size.upper())

# 输出
"A6"
```

### 验证规则

```yaml
allowed_values:
  - "A4"
  - "A5"
  - "A6"
  - "A7"
  - "B4"
  - "B5"
  - "B6"
  - "Pocket"
  - "Small"
  - "Medium"
  - "Large"
  - "One Size"
  - "Standard"

case:
  iso_sizes: "UPPER"  # A4, A5, A6
  word_sizes: "Title"  # Small, Medium, Large
```

---

## 🟤 规则 6：产地标准化映射

### 完整映射表

```yaml
# 亚洲
japan: "Japan"
jp: "Japan"
china: "China"
cn: "China"
prc: "China"
korea: "South Korea"
kr: "South Korea"
south_korea: "South Korea"
taiwan: "Taiwan"
tw: "Taiwan"
hong_kong: "Hong Kong"
hk: "Hong Kong"
thailand: "Thailand"
th: "Thailand"
vietnam: "Vietnam"
vn: "Vietnam"
india: "India"
in: "India"

# 北美
united_states: "United States"
us: "United States"
usa: "United States"
america: "United States"
canada: "Canada"
ca: "Canada"
mexico: "Mexico"
mx: "Mexico"

# 欧洲
united_kingdom: "United Kingdom"
uk: "United Kingdom"
gb: "United Kingdom"
britain: "United Kingdom"
great_britain: "United Kingdom"
germany: "Germany"
de: "Germany"
deutschland: "Germany"
france: "France"
fr: "France"
italy: "Italy"
it: "Italy"
spain: "Spain"
es: "Spain"
netherlands: "Netherlands"
nl: "Netherlands"
switzerland: "Switzerland"
ch: "Switzerland"
sweden: "Sweden"
se: "Sweden"
poland: "Poland"
pl: "Poland"

# 大洋洲
australia: "Australia"
au: "Australia"
new_zealand: "New Zealand"
nz: "New Zealand"
```

### 使用示例

```python
# 输入
input_country = "jp"

# 查找映射
standardized_country = COUNTRY_MAPPING.get(input_country.lower(), input_country.title())

# 输出
"Japan"
```

### 验证规则

```yaml
format: "Full country name"
case: "Title"
exceptions:
  - "United States"  # 不是 USA
  - "United Kingdom" # 不是 UK
  - "South Korea"    # 不是 Korea
```

---

## ⚫ 规则 7：默认值配置

### 全局默认值

```yaml
listing_defaults:
  # 商品状态
  condition: "NEW"
  
  # 物流设置
  handling_time: 2                    # 2 个工作日
  ship_to_locations:                  # 配送地区
    - "US"
    - "CA"
    - "GB"
    - "AU"
    - "JP"
  exclude_ship_to_locations: []       # 不排除地区
  
  # 促销设置
  promotional_shipping:
    threshold: 50                     # 满$50
    discount_percent: 100             # 免运费
  
  # 数量折扣
  quantity_discount:
    enabled: true
    tiers:
      - quantity: 2
        discount_percent: 10          # 买 2 件 9 折
      - quantity: 5
        discount_percent: 15          # 买 5 件 85 折
      - quantity: 10
        discount_percent: 20          # 买 10 件 8 折
  
  # 销售设置
  format: "FIXED_PRICE"
  marketplace_id: "EBAY_US"
  auto_publish: false                 # 需要预审核
  
  # 业务政策（从 config 读取）
  payment_policy_id: "265656298018"
  fulfillment_policy_id: "266026679018"
  return_policy_id: "265656303018"
  
  # 仓库位置
  merchant_location_key: "us-portland"
  
  # 图片设置
  image_upload:
    max_images: 12
    min_images: 1
    auto_add_shipping_info: true
    shipping_info_path: "templates/shipping_info.png"
  
  # 属性默认值
  attributes:
    default_brand: "Hobonichi"
    default_country: "Japan"
    default_condition: "NEW"
    default_currency: "USD"
```

### 字段级默认值

```yaml
field_defaults:
  sku:
    pattern: "{BRAND}-{YEAR}-{MODEL}-{COLOR}"
    auto_generate: true
  
  title:
    pattern: "{brand} {series} {year} {feature} {size}"
    max_length: 80
    auto_generate: true
  
  description:
    use_template: true
    template_file: "templates/listing_description.html"
  
  price:
    source: "cost_price"
    markup_percent: 50  # 成本价 × 1.5
  
  quantity:
    source: "inventory_system"
    default: 999  # 库存充足
  
  brand:
    source: "product_data"
    default: "Hobonichi"
  
  color:
    source: "product_data"
    standardize: true
  
  size:
    source: "product_data"
    standardize: true
  
  country_of_manufacture:
    default: "Japan"
```

---

## ⚪ 规则 8：验证规则

### SKU 验证

```yaml
sku:
  required: true
  pattern: "^[A-Z]{4}-\\d{4}-[A-Z0-9]{4,6}-[A-Z]{2}$"
  max_length: 50
  allowed_chars: "A-Z, 0-9, -"
  case: "UPPER"
  unique: true  # 店铺内唯一
  error_messages:
    pattern: "SKU 格式错误，应为：BRAND-YEAR-MODEL-COLOR"
    length: "SKU 不能超过 50 字符"
    unique: "SKU 已存在，请使用不同的 SKU"
```

### 标题验证

```yaml
title:
  required: true
  max_length: 80
  min_length: 10
  forbidden_chars: "<>&\"'"
  forbidden_words:
    - "free shipping"
    - "best price"
    - "cheap"
    - "discount"
  error_messages:
    length: "标题长度必须在 10-80 字符之间"
    forbidden: "标题不能包含促销信息或特殊字符"
```

### 价格验证

```yaml
price:
  required: true
  type: "number"
  min: 0.01
  max: 999999.99
  precision: 2
  currency: "USD"
  error_messages:
    range: "价格必须在 $0.01 - $999,999.99 之间"
    precision: "价格必须保留 2 位小数"
```

### 库存验证

```yaml
quantity:
  required: true
  type: "integer"
  min: 0
  max: 9999
  error_messages:
    range: "库存数量必须在 0-9999 之间"
    type: "库存数量必须是整数"
```

### 图片验证

```yaml
image_urls:
  required: false
  recommended: true
  min_count: 1
  max_count: 12
  protocol: "https"
  allowed_formats:
    - "jpg"
    - "jpeg"
    - "png"
    - "bmp"
    - "gif"
  min_dimension: 500
  recommended_dimension: 1600
  max_file_size_mb: 7
  error_messages:
    count: "图片数量必须在 1-12 张之间"
    protocol: "图片 URL 必须使用 HTTPS 协议"
    dimension: "图片尺寸不能小于 500px"
```

### 分类验证

```yaml
category_id:
  required: true
  type: "string"
  pattern: "^\\d+$"
  must_be_leaf: true
  error_messages:
    format: "分类 ID 必须是数字"
    leaf: "必须选择最底层分类（叶子分类）"
```

---

## 🔧 配置文件示例 (YAML)

```yaml
# generation_rules.yaml
# Listing 属性生成规则配置

version: "1.0"
updated: "2026-03-23"

# SKU 编码规则
sku:
  pattern: "{BRAND}-{YEAR}-{MODEL}-{COLOR}"
  brand_length: 4
  year_format: "YYYY"
  model_max_length: 6
  color_length: 2
  separator: "-"
  case: "UPPER"
  
  brand_codes:
    Hobonichi: "HOBO"
    Moleskine: "MOLE"
    Leuchtturm1917: "LEUC"
    Midori: "MIDO"
    Life: "LIFE"
    Traveler's Company: "TRAV"
    Kokuyo: "KOKU"
    Tombow: "TOMO"

# 标题生成规则
title:
  pattern: "{brand} {series} {year} {feature} {size}"
  max_length: 80
  mobile_display: 56
  truncate: true
  truncate_marker: "..."
  preserve_word: true
  
  priority:
    - brand
    - series
    - year
    - feature
    - size

# 分类映射
category:
  default: "1220"
  mapping:
    planner: "1221"
    notebook: "1222"
    journal: "1222"
    diary: "1221"
    stationery: "1220"
    organizer: "1220"
    book: "11450"
    collectible: "1"

# 颜色标准化
color:
  standardize: true
  case: "Title"
  mapping_file: "mappings/colors.yaml"

# 尺寸标准化
size:
  standardize: true
  iso_case: "UPPER"
  word_case: "Title"
  mapping_file: "mappings/sizes.yaml"

# 产地标准化
country:
  standardize: true
  case: "Title"
  mapping_file: "mappings/countries.yaml"

# 默认值
defaults:
  condition: "NEW"
  handling_time: 2
  currency: "USD"
  marketplace: "EBAY_US"
  format: "FIXED_PRICE"
  brand: "Hobonichi"
  country: "Japan"
  
  ship_to_locations:
    - "US"
    - "CA"
    - "GB"
    - "AU"
    - "JP"
  
  promotional_shipping:
    threshold: 50
    discount_percent: 100
  
  quantity_discount:
    enabled: true
    tiers:
      - quantity: 2
        discount_percent: 10
      - quantity: 5
        discount_percent: 15
      - quantity: 10
        discount_percent: 20

# 验证规则
validation:
  enabled: true
  strict_mode: false  # false=警告，true=错误
  
  rules:
    sku:
      required: true
      pattern: "^[A-Z]{4}-\\d{4}-[A-Z0-9]{4,6}-[A-Z]{2}$"
    
    title:
      required: true
      max_length: 80
      min_length: 10
    
    price:
      required: true
      min: 0.01
      max: 999999.99
    
    quantity:
      required: true
      min: 0
      max: 9999
    
    images:
      min_count: 1
      max_count: 12
      min_dimension: 500
```

---

## 📊 生成流程图

```
┌─────────────────┐
│  原始商品数据    │
│  (Excel/CSV)    │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  数据清洗        │
│  - 去除空格      │
│  - 统一大小写    │
│  - 填充空值      │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  属性标准化      │
│  - 颜色映射      │
│  - 尺寸映射      │
│  - 产地映射      │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  自动生成        │
│  - SKU 生成       │
│  - 标题生成      │
│  - 分类映射      │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  应用默认值      │
│  - 物流设置      │
│  - 业务政策      │
│  - 图片配置      │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  数据验证        │
│  - 格式检查      │
│  - 必填检查      │
│  - 业务规则      │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  生成结果        │
│  - Inventory    │
│  - Offer        │
│  - 预览确认      │
└─────────────────┘
```

---

## 📞 相关文件

- `EBAY_API_ATTRIBUTES.md` - API 字段完整说明
- `LISTING_ATTRIBUTES.md` - 属性清单和 HTML 模板
- `FIELD_GUIDE.md` - 字段使用指南
- `config.json` - 系统配置文件

---

## 🔄 更新日志

| 日期 | 版本 | 更新内容 |
|------|------|----------|
| 2026-03-23 | 1.0 | 初始版本，包含 8 大规则 |
