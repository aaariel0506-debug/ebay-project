# 规则更新建议 - 基于实际产品分析

> 根据已上架产品（Radiohead In Rainbows Vinyl）对照当前规则的调整建议
> 更新时间：2026-03-24

---

## 📊 产品对照分析

### 产品信息
- **商品**：Radiohead In Rainbows 10th Anniversary Limited Edition 10xVinyl Boxset
- **价格**：$49.00
- **分类**：Music > Vinyl Records
- **SKU**：待确认（截图中未显示）

---

## ⚠️ 发现的问题

### 1. ❌ 品类映射缺失

**当前规则只支持文具类：**
```yaml
category:
  planner: "1221"
  notebook: "1222"
  stationery: "1220"
  book: "11450"
```

**实际产品是音乐 Vinyl：**
```yaml
# 需要添加
category:
  music_vinyl: "176981"      # Vinyl Records
  music_cd: "176982"         # CDs
  music_cassette: "176983"   # Cassettes
  music_digital: "176984"    # Digital Music
```

### 2. ❌ 品牌/艺人映射缺失

**当前品牌表只有文具品牌：**
```yaml
brand_codes:
  Hobonichi: "HOBO"
  Moleskine: "MOLE"
  Leuchtturm1917: "LEUC"
```

**实际产品是音乐艺人：**
```yaml
# 需要添加艺人/乐队映射
artist_codes:
  Radiohead: "RADIO"
  Beatles: "BEAT"
  Pink Floyd: "PINK"
  Led Zeppelin: "LEDZ"
  ...
```

### 3. ❌ 属性字段不完整

**当前只支持文具属性：**
```yaml
aspects:
  - Brand
  - Model
  - Color
  - Size
  - Material
  - Type
```

**音乐产品需要：**
```yaml
# 需要添加音乐属性
music_aspects:
  required:
    - Artist/Group          # 艺人/乐队
    - Title                 # 专辑名
    - Format                # 格式 (Vinyl/CD/Cassette)
  
  optional:
    - Type                  # 类型 (Box Set/Album/Single)
    - Style                 # 风格 (Alternative Rock 等)
    - Release Year          # 发行年份
    - Record Label          # 唱片公司
    - Edition               # 版本 (Limited/Deluxe 等)
    - Speed                 # 转速 (33/45 RPM)
    - Number of Discs       # 碟片数量
```

### 4. ⚠️ 标题生成规则需要调整

**当前规则：**
```yaml
title:
  pattern: "{brand} {series} {year} {feature} {size}"
  max_length: 80
```

**实际产品标题结构：**
```
Radiohead In Rainbows 10th Anniversary Limited Edition 10xVinyl Boxset
结构：艺人 + 专辑名 + 周年纪念 + 版本 + 格式 + 类型
```

**建议调整为多品类支持：**
```yaml
title:
  patterns:
    # 文具类
    stationery: "{brand} {series} {year} {feature} {size}"
    
    # 音乐类
    music: "{artist} {album} {year} {edition} {format} {type}"
    
    # 图书类
    book: "{title} {subtitle} {author} {format} {year}"
    
    # 通用（自动选择最佳）
    default: "{brand} {product_type} {model} {feature} {size}"
  
  max_length: 80
  mobile_display: 56
```

### 5. ⚠️ 运费策略需要灵活配置

**当前配置：**
```yaml
promotional_shipping:
  threshold: 50          # 满$50
  discount_percent: 100  # 免运费
```

**实际产品：**
```yaml
# 直接免运费（无门槛）
shipping:
  free_shipping: true
  shipping_cost: 0
```

**建议调整为：**
```yaml
shipping:
  # 方案 A：满额免运费
  promotional:
    enabled: true
    threshold: 50
    discount_percent: 100
  
  # 方案 B：直接免运费
  free:
    enabled: false
    shipping_cost: 0
  
  # 方案 C：固定运费
  flat:
    enabled: false
    domestic: 5.00
    international: 15.00
```

### 6. ⚠️ 处理时间需要灵活配置

**当前配置：**
```yaml
handling_time: 2  # 固定 2 天
```

**实际产品：**
```yaml
handling_time: 3  # 3 天
```

**建议调整为按品类/商品配置：**
```yaml
handling_time:
  # 默认值
  default: 2
  
  # 按品类
  by_category:
    stationery: 2
    music: 3
    book: 2
  
  # 按商品特性
  by_feature:
    pre_order: 7        # 预售商品
    made_to_order: 5    # 定制商品
    in_stock: 2         # 现货
```

---

## 🔧 规则更新建议

### 更新 1：扩展分类映射

```yaml
category:
  default: "1220"
  
  # 文具类
  stationery:
    planner: "1221"
    notebook: "1222"
    journal: "1222"
    diary: "1221"
    organizer: "1220"
  
  # 音乐类（新增）
  music:
    vinyl: "176981"
    cd: "176982"
    cassette: "176983"
    digital: "176984"
    box_set: "176981"  # 盒装通常归类到具体格式
  
  # 图书类
  book:
    general: "11450"
    textbook: "360"
    children: "4"
  
  # 收藏品
  collectible:
    general: "1"
    music_memorabilia: "176985"
```

### 更新 2：扩展品牌/艺人映射

```yaml
# 品牌代码（文具）
brand_codes:
  Hobonichi: "HOBO"
  Moleskine: "MOLE"
  Leuchtturm1917: "LEUC"
  Midori: "MIDO"
  Life: "LIFE"
  Traveler's Company: "TRAV"
  Kokuyo: "KOKU"
  Tombow: "TOMO"

# 艺人代码（音乐，新增）
artist_codes:
  Radiohead: "RADIO"
  Beatles: "BEAT"
  Pink Floyd: "PINK"
  Led Zeppelin: "LEDZ"
  Queen: "QUEE"
  Michael Jackson: "MJ"
  Elvis Presley: "ELVI"
  Bob Dylan: "BOBD"
  Rolling Stones: "ROLL"
  Nirvana: "NIRV"
```

### 更新 3：SKU 编码规则扩展

```yaml
sku:
  # 文具类 SKU
  stationery:
    pattern: "{BRAND}-{YEAR}-{MODEL}-{COLOR}"
    example: "HOBO-2026-S2610-BL"
  
  # 音乐类 SKU（新增）
  music:
    pattern: "{ARTIST}-{ALBUM}-{YEAR}-{FORMAT}"
    example: "RADIO-INRAINBOWS-2017-VINYL"
    
    # 如果太长，使用缩写
    abbreviations:
      Anniversary: "ANNIV"
      Limited Edition: "LTD"
      Deluxe: "DLX"
      Remastered: "REM"
      Collector's Edition: "COL"
  
  # 图书类 SKU（新增）
  book:
    pattern: "{AUTHOR}-{TITLE}-{YEAR}-{FORMAT}"
    example: "MURAKAMI-KAFKA-2005-HC"
```

### 更新 4：属性映射扩展

```yaml
aspects:
  # 文具属性
  stationery:
    required:
      - Brand
      - Type
      - Size
    optional:
      - Model
      - Color
      - Material
      - Features
  
  # 音乐属性（新增）
  music:
    required:
      - Artist/Group
      - Title
      - Format
    optional:
      - Type
      - Style
      - Release Year
      - Record Label
      - Edition
      - Speed
      - Number of Discs
  
  # 图书属性（新增）
  book:
    required:
      - Author
      - Title
      - Format
    optional:
      - Publisher
      - Publication Year
      - Language
      - ISBN
      - Edition
```

### 更新 5：物流配置扩展

```yaml
shipping:
  # 方案 A：满额免运费
  promotional:
    enabled: true
    threshold: 50
    discount_percent: 100
  
  # 方案 B：直接免运费
  free:
    enabled: false
  
  # 方案 C：固定运费
  flat_rate:
    enabled: false
    domestic: 5.00
    international: 15.00
  
  # 按品类配置（新增）
  by_category:
    stationery:
      handling_time: 2
      free_shipping_threshold: 50
    music:
      handling_time: 3
      free_shipping_threshold: 0  # 直接免运费
    book:
      handling_time: 2
      free_shipping_threshold: 35
```

---

## 📋 下一步行动

### 阶段 1：确认品类策略
- [ ] 确认是否需要支持多品类（文具 + 音乐 + 图书...）
- [ ] 确认每个品类的优先级
- [ ] 确认品类识别规则（如何自动判断品类）

### 阶段 2：补充映射表
- [ ] 补充音乐类分类映射
- [ ] 补充艺人/乐队代码映射
- [ ] 补充音乐属性字段
- [ ] 补充音乐标题生成规则

### 阶段 3：配置灵活性
- [ ] 实现按品类配置物流策略
- [ ] 实现按品类配置处理时间
- [ ] 实现按品类配置运费策略

### 阶段 4：测试验证
- [ ] 用 Radiohead Vinyl 产品测试音乐品类
- [ ] 用 Hobonichi 测试文具品类
- [ ] 验证品类自动识别
- [ ] 验证属性自动生成

---

## ❓ 需要确认的问题

1. **品类范围**
   - 只做文具，还是多品类都做？
   - 如果是多品类，优先级是什么？

2. **SKU 规则**
   - 文具和音乐是否使用不同的 SKU 规则？
   - 是否需要统一的 SKU 格式？

3. **属性映射**
   - 音乐产品的属性字段是否需要全部支持？
   - 是否还有其他品类需要支持？

4. **物流策略**
   - 不同品类是否需要不同的处理时间？
   - 运费策略是否按品类区分？

5. **标题生成**
   - 是否需要按品类使用不同的标题模板？
   - 还是使用通用模板？

---

## 📞 相关文件

- `GENERATION_RULES.md` - 当前规则（需要更新）
- `EBAY_API_ATTRIBUTES.md` - API 字段说明
- `LISTING_ATTRIBUTES.md` - 属性清单
- `config.json` - 系统配置
