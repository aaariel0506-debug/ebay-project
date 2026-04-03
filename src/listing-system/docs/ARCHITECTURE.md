# Listing API 发布系统 — 架构文档 v1.0

> 基于 Superpowers 流程：读取商品表 → 生成内容 → 预审核 → 上架 → 回写结果

---

## 一、系统全貌

```
Google Drive: 08 ebay-project/ebay listing API/
├── eBay API Listing V1.0          ← 商品源数据表（待填商品）
├── eBay Description Template        ← 描述模板
├── input/                          ← 原始文件入口
└── [SKU_商品名的文件夹]/           ← 每个商品一个文件夹
    ├── listing_content.html         ← Listing 内容（图片+描述）
    ├── review_data.json            ← 审核数据结构
    └── images/                     ← 商品图片

本地: src/listing-system/
├── main.py                         ← 流程总控
├── create_listing.py               ← eBay API 发布逻辑
├── review_web.py                   ← 预审核页面
├── upload_drive.py                 ← Google Drive 上传
├── scripts/
│   ├── make_config.py              ← 生成 config.json
│   ├── fetch_product_from_url.py   ← 从 EC 链接抓取商品信息
│   ├── fetch_upc.py                ← 从最安値查询 UPC
│   └── generate_listing_content.py ← 生成 Listing 内容
└── docs/
    ├── ARCHITECTURE.md             ← 本文档
    └── 参数表/                     ← 业务参数
```

---

## 二、Step 流程详解

### Step 1 — 读取商品列表

**来源：** Google Drive `eBay API Listing V1.0`

**字段来源映射：**

| Excel 列 | 字段名 | 来源 | 处理方式 |
|----------|--------|------|----------|
| A | EC site URL | 手动填入 | 抓取商品信息 |
| B | eBay URL | 手动填入 | 上架后更新 |
| C | SKU | 手动填入 | 主键 |
| D | 刊登 | 手动填入 | 筛选条件："刊登=是"才处理 |
| G | UPC | 程序查询 | 从最安値网站抓取 |
| H | 广告费 | 手动填入 | eBay广告比例（%） |
| I | 价格折扣 | 手动填入 | 折扣比例 |
| J | 采购价格（日） | 手动填入 | JPY |
| K | JP重量(g) | 手动填入 | g |
| L | 长（cm） | 手动填入 | cm |
| M | 宽（cm） | 手动填入 | cm |
| N | 高（cm） | 手动填入 | cm |
| P | 销售价格 USD | 手动填入 | **必填** |
| R | 物流定价 US | 手动填入 | **必填** |
| W | eBay佣金 | 手动填入 | % |

**自动计算字段（程序算出，不在源表填）：**

| 字段 | 计算公式 |
|------|---------|
| OC重量 | =max(L×M×N/8000×1000, K) |
| 物流费用 US外 | =F(重量, 体积) |
| SP运费 | =P×参数.关税×(1+参数.关税手续费)×B1+通关手续费 |
| 关税及手续费 | =P×0.1×(1+0.021)×B1+225 |
| 总价US | =P+R |
| 增加成本US | =(V+U-Q)/B1 |
| 海外手数料 | =参数.海外手数料率 |
| 利润（US外） | =(P×(1-I)-AE)×B1-J-Q |
| 利润率（US外） | =Y/P/B1 |
| ROI（US外） | =Y/J |
| 利润（US） | =(P×(1-I)+R-AF)×B1-J-U-V |
| eBay费用（US外） | =P×(1-I)×1.1×(W+X+H)×1.1+0.4×1.1 |
| eBay费用（US） | =(P×(1-I)×1.1+R)×(W+X+H)×1.1+0.4×1.1 |

---

### Step 2 — 生成 Listing 内容 → 等待审核

**输出位置：** Google Drive `ebay listing API/[SKU]_[商品名的文件夹/`

**每个 SKU 生成：**

```
[SKU]_商品名/
├── listing_content.html     # 完整 Listing HTML（标题+描述+图片）
├── review_data.json        # 审核数据（结构化，方便前端渲染）
└── images/                 # 下载到本地的商品图片
    ├── main.jpg
    ├── image_02.jpg
    └── ...
```

**内容生成规则：**
- 标题：SEO优化，不超过80字符（eBay限制）
- 描述：从 EC 链接抓取 + 翻译优化 + 结构化 HTML
- 图片：从 EC 链接抓取，下载到本地或用线上 URL
- 分类：由 SKU 前缀或其他规则确定分类 ID

---

### Step 3 — 预审核页面

**本地运行：** `python3 review_web.py` → http://localhost:8080

**审核页面功能：**
1. 列出所有 Google Drive 上 `[SKU]_*/review_data.json` 还未审核的商品
2. 显示 Listing 完整内容（标题、描述、价格、图片、所有字段）
3. **可调整所有参数**：价格、广告费、分类、图片、描述等
4. 点"确认发布" → 写入 eBay API

**字段映射（review_data.json → eBay API）：**

| review_data 字段 | eBay API 字段 |
|-----------------|--------------|
| sku | sku |
| title | title（InventoryItem.product.title） |
| description | description（HTML） |
| category_id | categoryId |
| price | pricingSummary.price.value |
| quantity | quantity |
| condition | condition |
| image_urls[] | product.imageUrls[] |
| brand | product.aspects.Brand |
| mpn | product.aspects.MPN |
| weight | weight（kg） |
| dimensions | packageDimensions |

---

### Step 4 — 上架 + 回写结果

**发布后回写：**
- `eBay URL` → eBay 商品链接
- `刊登` 状态 → "上架完成" 或 timestamp
- `备注` → 上架时间戳 + offer_id

---

## 三、模块职责

| 模块 | 职责 | 入口 |
|------|------|------|
| `fetch_product.py` | 从 EC URL 抓取标题、描述、图片 | Step 1 |
| `fetch_upc.py` | 从最安値查询 UPC | Step 1 |
| `generate_content.py` | 生成 listing HTML + review JSON | Step 2 |
| `upload_to_drive.py` | 上传内容到 Google Drive | Step 2 |
| `review_web.py` | Flask 预审核页面 | Step 3 |
| `create_listing.py` | eBay API 发布 | Step 4 |
| `main.py` | 流程总控 | CLI |

---

## 四、eBay API 发布参数

| 字段 | 值 |
|------|-----|
| environment | production |
| marketplace | EBAY_US |
| currency | USD |
| payment_policy_id | 265656298018 |
| fulfillment_policy_id | 266026679018 |
| return_policy_id | 265656303018 |
| condition | NEW (1000) |
| format | FIXED_PRICE |
| status | UNPUBLISHED（草稿，预审核后改为 PUBLISHED）|

---

## 五、Google Drive 结构

```
08 ebay-project/ebay listing API/
├── eBay API Listing V1.0         ← 商品源数据（Google Sheets）
├── eBay Description Template       ← 描述模板
├── input/                         ← 原始文件输入目录
└── [SKU]_[商品名]/               ← 每个商品一个审核文件夹
    ├── listing_content.html
    ├── review_data.json
    └── images/
```

**Google Drive 文件夹 ID：**
- listing API 根目录: `15h280yccE1bN4gzTuAM-QlxI1sCRqdGu`
- input 目录: `19s3Ps0TIbhG8reURL98tdpYCWp8_Mwid`

---

## 六、商品分类参考

| 商品类型 | Category ID | Category Name |
|----------|-------------|---------------|
| Tarot Cards / Oracle Cards | 35837 | Wicca, Pagan & Tarot Supplies |
| Hobonichi Products | 45112 | Paper & Page Additions |
| Default fallback | 262302 | Everything Else |

分类 ID 需要在 review 页面可手动调整。

---

## 七、状态机

```
[源表: 刊登=是]
       ↓ (Step 1: 读取)
[生成内容]
       ↓ (Step 2: 上传 Drive)
[review_data.json 存在]
       ↓ (Step 3: 预审核确认)
[已发布: status=PUBLISHED]
       ↓ (Step 4: 回写)
[源表: eBay URL + 刊登=完成]
```

---

## 八、待开发清单

1. [ ] `fetch_product.py` — 从 EC URL 抓取商品原始信息
2. [ ] `fetch_upc.py` — 从最安値网站查询 UPC
3. [ ] `generate_content.py` — 根据模板生成 listing 内容
4. [ ] 重构 `review_web.py` — 对接新的 review_data.json 格式
5. [ ] 重构 `main.py` — 串联 Step 1→2→4（跳过 Step 3 本地审核）
6. [ ] Step 2 结果上传到 Google Drive 的 per-product 文件夹
7. [ ] Step 4 回写结果到源表（Google Sheets）
8. [ ] UPC 查询安居值网站逻辑
9. [ ] 分类 ID 规则引擎（根据 SKU 或 EC 链接判断）
