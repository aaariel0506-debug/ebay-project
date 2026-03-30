# eBay Listing 属性生成规则 v2.0（基于实际数据修正）

> 基于 166 个已上架商品、295 条销售记录的实际数据分析
> 替代之前假设的文具专用规则
> 更新时间：2026-03-25

---

## 📊 店铺实际数据概览

### 品类分布
| 品类 | 销量 | 占比 | 示例商品 |
|------|------|------|----------|
| 手帐/Planner | 83 | 28% | MUJI Planner, Hobonichi Techo |
| 锯/Saw | 57 | 19% | Silky Katanaboy, Gomboy, Bigboy |
| 其他 | 46 | 16% | 杂货、日用品 |
| 卡牌/Card | 30 | 10% | One Piece TCG, amiibo |
| 音乐/影视 | 28 | 9% | CD, Vinyl, Blu-ray |
| 文具/Stationery | 21 | 7% | 笔、剪刀、文具套装 |
| 钓具/Fishing | 15 | 5% | HIDEUP COIKE 路亚 |
| 模型/Figure | 11 | 4% | 手办、模型车 |
| 日用品/Daily | 4 | 1% | 耳机、剃须刀 |

### 主要品牌
| 品牌 | 销量 | 主营品类 |
|------|------|----------|
| MUJI | 45 | 手帐 |
| Hobonichi | 43 | 手帐 |
| Silky | 41 | 锯 |
| One Piece | 23 | 卡牌 |
| HIDEUP | 12 | 钓具 |
| JVC | 6 | 耳机 |

---

## 🔴 规则 1：SKU 编码规则（已修正）

### 实际格式
```
{STORE_ID}-{YYMM}-{SEQ}[_{VARIANT}]
```

### 字段说明

| 字段 | 长度 | 规则 | 示例 |
|------|------|------|------|
| `STORE_ID` | 2 位 | 店铺/账号代码，固定 `01` | `01` |
| `YYMM` | 4 位 | 上架年月 (25=2025, 26=2026) | `2509`, `2601`, `2512` |
| `SEQ` | 4 位 | 序号，从 0001 递增 | `0001`, `0098`, `0232` |
| `VARIANT` | 可选 | 变体后缀，下划线分隔 | `_Wh`, `_Da`, `_Pi`, `_#1` |

### 格式解读

```
01-2509-0098
│  │     │
│  │     └── 序号 0098（该月第 98 个商品）
│  └── 2025 年 9 月上架
└── 店铺代码 01

01-2509-0027_Wh
│  │     │    │
│  │     │    └── 变体后缀：White
│  └──── └── 2025 年 9 月，第 27 号
└── 店铺代码 01

01-2512-0115_#14
│  │     │    │
│  │     │    └── 变体后缀：颜色编号 #14
│  └──── └── 2025 年 12 月，第 115 号
└── 店铺代码 01
```

### 验证规则

```yaml
# 基础 SKU
pattern: "^\\d{2}-\\d{4}-\\d{4}$"
example: "01-2509-0098"

# 带变体 SKU
pattern_variant: "^\\d{2}-\\d{4}-\\d{4}[_-].+$"
example: "01-2509-0027_Wh"

# 通用匹配
pattern_all: "^\\d{2}-\\d{4}-\\d{4}([_-].+)?$"
```

### 变体后缀规则

| 变体类型 | 后缀格式 | 示例 |
|----------|----------|------|
| 颜色（英文缩写） | `_{Color}` | `_Wh` (White), `_Da` (Dark), `_Pi` (Pink) |
| 颜色（编号） | `_#{N}` | `_#1`, `_#12`, `_#14` |
| 颜色（英文全称） | `_{color}` | `_ye` (yellow), `_wh2` (white variant 2) |
| 尺寸 | `_{Size}` | `_A5`, `_A6`, `_We` (Weekly) |
| 其他 | `_{desc}` | `-SS` (Sticker Set) |

### 自动生成逻辑

```python
def generate_sku(store_id="01", year_month=None, seq=None, variant=None):
    """
    生成 SKU
    store_id: 店铺代码（默认 01）
    year_month: 上架年月（如 2603 = 2026年3月）
    seq: 序号（自动递增）
    variant: 变体后缀（可选）
    """
    if year_month is None:
        from datetime import datetime
        now = datetime.now()
        year_month = f"{now.year % 100:02d}{now.month:02d}"
    
    if seq is None:
        seq = get_next_seq(store_id, year_month)  # 从数据库/文件获取
    
    sku = f"{store_id}-{year_month}-{seq:04d}"
    
    if variant:
        sku += f"_{variant}"
    
    return sku

# 示例输出
# generate_sku()                          → "01-2603-0001"
# generate_sku(variant="Wh")              → "01-2603-0001_Wh"
# generate_sku(variant="#3")              → "01-2603-0001_#3"
```

---

## 🟡 规则 2：标题生成规则（已修正）

### 实际标题结构分析

通过分析 166 个商品标题，提取出以下模式：

#### 模式 A：手帐类
```
{Brand} {Year} Planner {Size} {Type} {Feature} {Pages} Japan {Condition} {Colors}
示例：MUJI 2026 Planner B6 Monthly/Weekly Monday Start Dec 2025 176p Japan NEW 3 Color
示例：Hobonichi Techo 2026 Weeks English Version Yumi Kitagishi White Cat Jan Start
```

#### 模式 B：工具类
```
{Brand} {Product} {Spec} {Feature} {Model} Japan {Condition}
示例：Silky Katanaboy 500 Folding Saw 403-50 20" XL Teeth Bushcraft Big Log Japan New
示例：Silky Gomboy Replacement Blade 240mm Medium Teeth Folding Saw 122-24 Japan New
```

#### 模式 C：卡牌/收藏类
```
{IP} {Product} {Set/Edition} {TCG} {Condition} Japan {Brand}
示例：UNION ARENA BLEACH Thousand-Year Blood War New Card Selection TCG Set Bandai JPN
示例：One Piece Card Game McDonald's 2025 Promo Complete Set P-101-106 Luffy Ace Japan
```

#### 模式 D：音乐/影视类
```
{Artist} {Album} Japan {Format} {Feature} {Condition} {OBI}
示例：Kanye West Graduation Japan CD OBI Sealed Bittersweet Poetry Good Night Bonus
示例：Hilary Duff Luck or Something Japan CD Mega Jacket Bonus Track Obi New 2025
示例：Radiohead In Rainbows 10th Anniversary Limited Edition 10xVinyl Boxset
```

#### 模式 E：钓具类
```
{Brand} {Product} {Spec} {Feature} Japan {Condition}
示例：HIDEUP COIKE 17mm JDM Finesse Bass Lure #143 Watermelon Black Blue F New
```

#### 模式 F：通用（日用品/杂货）
```
{Brand} {Product} {Spec} {Feature} Japan {Condition}
示例：One Piece Luffy Face Changing Pen Ver 2 Action Ballpoint Funbox Japan 4 Faces
示例：KAI Seki Magoroku Tweezers Slant Tip Precision Eyebrow Hair Removal Japan HC3506
```

### 标题通用规则

```yaml
max_length: 80
mobile_display: 56

# 通用结构
structure:
  - brand/artist      # 品牌或艺人名
  - product_name      # 产品名称
  - spec/model        # 规格或型号
  - feature           # 核心卖点
  - origin            # 产地标记（Japan/JPN/JDM）
  - condition         # 新旧（NEW/New/Sealed）

# 常用关键词（提升搜索排名）
keywords:
  origin: ["Japan", "JPN", "JDM", "Japanese"]
  condition: ["NEW", "New", "Sealed", "Authentic"]
  exclusive: ["Japan Exclusive", "Japan Limited"]
  bonus: ["Bonus", "OBI", "w/ OBI"]

# 禁止词
forbidden:
  - "Free Shipping"
  - "Best Price"
  - "Cheap"
  - "L@@K"
```

---

## 🟢 规则 3：分类映射规则（已修正）

### 按实际商品扩展

```yaml
category:
  # 手帐/文具类
  planner: "172008"          # Planners & Organizers
  notebook: "1222"           # Notebooks & Writing Pads
  stationery: "1220"         # Stationery & Office Supplies
  pen: "1221"                # Pens & Writing Instruments
  scissors: "25395"          # Scissors

  # 工具类
  saw: "122838"              # Hand Saws
  blade: "122838"            # Saw Blades → Hand Saws
  folding_saw: "122838"      # Folding Saws
  
  # 卡牌/游戏类
  tcg: "183454"              # CCG Individual Cards
  card_game: "183454"        # Card Games
  booster_box: "183456"      # Sealed Booster Boxes
  amiibo: "183462"           # amiibo Cards
  
  # 音乐/影视类
  cd: "176984"               # CDs
  vinyl: "176981"            # Vinyl Records
  bluray: "617"              # Blu-ray Discs
  
  # 钓具类
  fishing_lure: "36149"      # Baits & Lures
  soft_lure: "36149"         # Soft Baits
  
  # 模型/手办类
  figure: "158666"           # Action Figures
  diecast: "222"             # Diecast Vehicles
  model_kit: "1187"          # Model Kits
  
  # 日用品
  headphones: "112529"       # Headphones
  razor: "67863"             # Razors
  beauty: "11838"            # Skin Care
  
  # 默认
  default: "1220"            # Stationery
```

---

## 🔵 规则 4：属性映射规则（按品类）

### 手帐/Planner 属性

```yaml
planner:
  required:
    Brand: "{brand}"           # MUJI, Hobonichi
    Type: "Planner"
  optional:
    Size: "{size}"             # A5, A6, B6
    Features: "{features}"     # Monthly, Weekly, etc.
    Year: "{year}"             # 2026
    Country/Region of Manufacture: "Japan"
    Color: "{color}"           # 变体颜色
    Pages: "{pages}"           # 176p
```

### 工具/Saw 属性

```yaml
saw:
  required:
    Brand: "{brand}"           # Silky
    Type: "{type}"             # Folding Saw, Replacement Blade
  optional:
    Model: "{model}"           # 403-50, 294-30
    Blade Length: "{length}"   # 500mm, 240mm
    Features: "{features}"     # Coarse Teeth, Fine Teeth
    Country/Region of Manufacture: "Japan"
    MPN: "{mpn}"
```

### 卡牌/TCG 属性

```yaml
card:
  required:
    Game: "{game}"             # One Piece, UNION ARENA
    Set: "{set}"               # Premium Collection
  optional:
    Card Type: "{type}"        # Booster Box, Single Card
    Language: "{language}"     # Japanese, English
    Year Manufactured: "{year}"
    Country/Region of Manufacture: "Japan"
    Features: "{features}"     # Sealed, Promo
```

### 音乐/CD/Vinyl 属性

```yaml
music:
  required:
    Artist/Group: "{artist}"   # Radiohead, Kanye West
    Title: "{album}"           # In Rainbows, Graduation
    Format: "{format}"         # CD, Vinyl, Blu-ray
  optional:
    Type: "{type}"             # Album, Single, Box Set
    Style: "{genre}"           # Alternative Rock, Hip-Hop
    Release Year: "{year}"
    Record Label: "{label}"
    Edition: "{edition}"       # Limited Edition, Remaster
    Country/Region of Manufacture: "Japan"
    Features: "{features}"     # OBI, Bonus Track, Sealed
```

### 钓具/Fishing 属性

```yaml
fishing:
  required:
    Brand: "{brand}"           # HIDEUP
    Type: "Soft Plastic Lure"
  optional:
    Model: "{model}"           # COIKE 17mm
    Color: "{color}"           # Watermelon Black Blue
    Features: "{features}"     # Finesse, FECO
    Country/Region of Manufacture: "Japan"
```

### 通用属性

```yaml
general:
  required:
    Brand: "{brand}"
  optional:
    Type: "{type}"
    Model: "{model}"
    Color: "{color}"
    Country/Region of Manufacture: "Japan"
    Features: "{features}"
    MPN: "{mpn}"
    UPC: "{upc}"
```

---

## ⚫ 规则 5：默认值配置（已修正）

```yaml
defaults:
  # 商品状态
  condition: "NEW"
  
  # 物流设置
  handling_time: 3               # 修正为 3 天（实际使用值）
  ship_from: "Japan"
  
  # 运费策略
  shipping:
    free_shipping: true          # 默认免运费（根据实际产品）
    domestic_shipping: 0
    international_shipping: 0
  
  # 销售设置
  format: "FIXED_PRICE"
  marketplace_id: "EBAY_US"
  currency: "USD"
  auto_publish: false
  
  # 业务政策
  payment_policy_id: "265656298018"
  fulfillment_policy_id: "266026679018"
  return_policy_id: "265656303018"
  
  # 仓库位置
  merchant_location_key: "us-portland"
  
  # 产地
  default_country: "Japan"
  
  # 图片
  auto_add_shipping_info: true
  shipping_info_image: "templates/shipping_info.png"
```

---

## ⚪ 规则 6：验证规则（已修正）

```yaml
validation:
  sku:
    pattern: "^\\d{2}-\\d{4}-\\d{4}([_-].+)?$"
    max_length: 50
    error: "SKU 格式应为 01-YYMM-NNNN 或 01-YYMM-NNNN_变体"
  
  title:
    max_length: 80
    min_length: 15
    must_contain_one_of:
      - "Japan"
      - "JPN"
      - "Japanese"
      - "JDM"
    forbidden:
      - "free shipping"
      - "best price"
      - "cheap"
    error: "标题 15-80 字符，建议包含 Japan/JPN 关键词"
  
  price:
    min: 5.00
    max: 999.99
    currency: "USD"
  
  quantity:
    min: 1
    max: 999
    default: 1
  
  images:
    min_count: 1
    max_count: 12
    min_dimension: 500
    recommended_dimension: 1600
```

---

---

## 📋 规则 7：完整上品 SOP（来自实际工作文档）

> 来源：Listing SOP 文档（docs/listing_sop.docx）

### 一、选品流程

#### 选品渠道
1. **eBay Research** - 后台 Product Research，搜索关键词（如"cd japan"），筛选 New + Fixed Price + Seller Location: Japan
2. **Zik Analytics** - 竞争对手分析，查看对标店铺近 14/30 天销售商品
3. **日本亚马逊/乐天** - 品类热销榜单前 100

#### 选品禁忌
- ❌ 体积大重量轻的商品
- ❌ 预售商品（presale/psl）
- ❌ 食品类、按摩类、液体类
- ⚠️ 带锂电池需备注
- ✅ 优先全新商品

### 二、Listing 维护（Excel 定价）

#### Excel 表格字段
| 列 | 字段 | 说明 |
|----|------|------|
| A | 对标 eBay 链接 | 参考商品 |
| B | 货源链接 | 采购地址 |
| C | ItemID | 商品编号 → 填入 eBay 的 Custom Label (SKU) |
| F | EC site | 货源网站 |
| G | UPC | 商品条形码 |
| K | 采购价格 | 日元 |
| L | 销售价格 | USD |
| M | 重量 | 克，向上取整一档（如 80g→110g, 190g→210g） |
| P | 物流定价 | 运费档位 |
| Q | 增加成本 | 参考值 |
| Y | ROI US外 | 利润率，目标 20-35%，低单价可到 60% |
| AB | ROI US | 美国利润率，需大于 Y 列 |

#### 定价规则
```yaml
pricing:
  roi_target:
    min: 20%
    max: 35%
    low_price_exception: 60%  # 单价 <1000 日元的商品
  
  shipping:
    base: "Q列（增加成本）"
    markup: "向上浮动 1-2 档"
    example: "Q=10.85 → P=12.99 或 15.99"
  
  shipping_method:
    default: "JP-Epacket"     # 95% 商品
    heavy: "sp-Economy"       # 1500g 以上
```

### 三、Listing 刊登流程

#### 步骤 1：AI 生成标题和描述
```
工具：Gemini 2.5 Pro
Prompt：
"以下是产品信息，严格按照模板《eBay Description Template 1005》
生成html格式的英文商品介绍（美式用词,请检查代码里不要有错误代码出现），
和seo优化过的ebay标题（标题不超过80个字符，并且尽可能用满80个字符，
重点词尽可能放在前56个字）"

输入：亚马逊产品标题 + 商品介绍 + A+ 文字
```

#### 步骤 2：eBay 后台刊登
```yaml
操作流程:
  1. Creating Listing → 输入对标商品链接 → Search
  2. 选择同款商品 → 商品状态选 Brand New
  3. 上传图片：
     - 亚马逊大图（右键复制图片地址）
     - Google 图片搜索（日语名称）
     - 本地上传 DDP 配图（运费说明图）
     - 每个商品至少 2 张图片
  4. Item Title → 粘贴 AI 生成的标题
  5. Custom Label (SKU) → 粘贴 Listing 表格 C 列
  6. Store Category → 选择对应分类
  7. Item Specifics → 大部分从对标商品继承，Apply All
  8. Description → 勾选 Show HTML Code → 粘贴 AI 生成的 HTML
  9. Pricing：
     - Buy It Now → Listing L 列
     - Quantity → 2
     - Shipping Policy → Listing P 列
  10. Display on eBay UK → 默认不勾选
  11. Country of Origin → Japan
  12. Promote → General 5%（如已开通）
  13. Preview → List it
```

#### 步骤 3：多变体发布
```yaml
variations:
  - 每个变体单独准备 1-2 张图片
  - 变体属性不能出现在主属性中（冲突）
  - 变体 SKU 每个单独生成
  - 变体价格和数量统一输入
```

### 四、标题生成规则（Gemini Prompt）

```yaml
title:
  max_length: 80
  target_length: 80           # 尽可能用满 80 字符
  seo_priority: 56            # 重点词放在前 56 字符
  language: "English (US)"
  
  generation:
    tool: "Gemini 2.5 Pro"
    template: "eBay Description Template 1005"
    input: "亚马逊产品标题 + 商品介绍 + A+ 文字"
```

### 五、HTML 描述规则

```yaml
description:
  format: "HTML"
  template: "eBay Description Template 1005"
  language: "English (US)"
  
  must_include:
    - 商品介绍
    - 注意事项
    - Shipping 信息
    - Return 信息
  
  verification:
    tool: "html在线运行 (toolhelper.cn)"
    check:
      - 无乱码
      - 内容完整
      - 无错误代码
```

### 六、eBay 刊登必填项总结

| 字段 | 来源 | 说明 |
|------|------|------|
| **标题** | Gemini 生成 | ≤80 字符，SEO 优化 |
| **SKU** | Listing 表 C 列 | `01-YYMM-NNNN` 格式 |
| **图片** | 亚马逊/Google/本地 | ≥2 张 + DDP 配图 |
| **分类** | Store Category | 手动选择 |
| **Item Specifics** | 对标商品继承 | Apply All + 检查 |
| **描述** | Gemini HTML | 模板 1005 |
| **价格** | Listing 表 L 列 | Buy It Now |
| **数量** | 固定 2 | 默认库存 |
| **运费** | Listing 表 P 列 | 运费政策 |
| **UK 展示** | 勾选 | 扩大曝光 |
| **产地** | Japan | 必填 |
| **广告** | 5% | General Promote |
| **UPC** | 最安値查询 | Listing 表 G 列 |

---

## 📊 与旧规则对比

| 项目 | v1.0（旧） | v2.0（新） | 变化 |
|------|-----------|-----------|------|
| SKU 格式 | `HOBO-2026-S2610-BL` | `01-2509-0098` | 完全不同 |
| 品类支持 | 仅文具 | 9 大品类 | 大幅扩展 |
| 品牌数量 | 8 个文具品牌 | 多品类品牌 | 大幅扩展 |
| 标题模式 | 1 个固定模式 | 6 个品类模式 | 大幅扩展 |
| 分类映射 | 4 个文具分类 | 20+ 分类 | 大幅扩展 |
| 处理时间 | 2 天 | 3 天 | 修正 |
| 运费策略 | 满$50 免运费 | 运费表档位 | 修正 |
| 属性字段 | 文具专用 | 按品类区分 | 大幅扩展 |
| 默认数量 | 不固定 | 2 | 修正 |
| AI 生成 | 无 | Gemini 2.5 Pro | 新增 |
| 描述模板 | 自定义 | Template 1005 | 修正 |
| UPC 来源 | 无 | 最安値查询 | 新增 |
| 广告 | 无 | General 5% | 新增 |
| UK 展示 | 无 | 默认勾选 | 新增 |
