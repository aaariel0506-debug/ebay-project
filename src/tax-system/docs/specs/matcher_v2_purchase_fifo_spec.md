# 采购匹配 v2 规格书 — 三层匹配 + FIFO 成本分配

**版本：** v2.0  
**生成日期：** 2026-03-18  
**状态：** 待实现  
**优先级：** P1（最高）

---

## 1. 概述

本规格书定义采购记录与 eBay 订单的三层匹配策略，以及基于 FIFO（先进先出）的库存成本分配机制。

### 1.1 目标
- 提高采购↔订单匹配覆盖率（目标 ≥ 40%）
- 支持同一商品多次采购、多次销售的 FIFO 成本核算
- 生成精确的单品利润报表

### 1.2 匹配策略（三层）

| 层级 | 名称 | 描述 | 置信度 |
|------|------|------|--------|
| Layer 1 | 锚点精确匹配 | ASIN / SKU / 追踪号精确匹配 | 1.0 |
| Layer 2 | 品牌词典模糊匹配 | 使用日英品牌对照表 + 商品名模糊匹配 | 0.7 ~ 0.95 |
| Layer 3 | 日期窗口过滤匹配 | 在采购日期±7 天窗口内，匹配相似商品 + 价格接近 | 0.5 ~ 0.7 |

---

## 2. Layer 2: 品牌词典

### 2.1 品牌对照表结构

文件：`matcher/brand_dict.py`

```python
BRAND_DICT = {
    "バンダイ": ["Bandai", "BANDAI"],
    "タカラトミー": ["Takara Tomy", "TAKARA TOMY"],
    "セガ": ["Sega", "SEGA"],
    "カプコン": ["Capcom", "CAPCOM"],
    "スクウェア・エニックス": ["Square Enix", "SQUARE ENIX"],
    "任天堂": ["Nintendo", "NINTENDO"],
    "ソニー": ["Sony", "SONY"],
    # ... 更多品牌
}
```

### 2.2 使用方式

```python
from matcher.brand_dict import BRAND_DICT, normalize_brand

def normalize_brand(brand_jp: str) -> list[str]:
    """将日文品牌名转换为英文别名列表"""
    return BRAND_DICT.get(brand_jp, [brand_jp])
```

---

## 3. 数据库变更

### 3.1 purchase_order_links 表新增字段

```sql
ALTER TABLE purchase_order_links ADD COLUMN allocated_qty INTEGER DEFAULT NULL;
ALTER TABLE purchase_order_links ADD COLUMN allocated_cost_jpy REAL DEFAULT NULL;
ALTER TABLE purchase_order_links ADD COLUMN allocated_tax_jpy REAL DEFAULT NULL;
```

### 3.2 新建 inventory 表

```sql
CREATE TABLE IF NOT EXISTS inventory (
    id TEXT PRIMARY KEY,              -- amazon_jp_{ASIN}_{batch_date}
    item_sku TEXT,                    -- ASIN
    item_name TEXT,                   -- 日文商品名
    item_name_en TEXT,                -- 英文商品名
    total_quantity INTEGER,           -- 累计采购数量
    sold_quantity INTEGER DEFAULT 0,  -- 已销售数量
    remaining_quantity INTEGER,       -- 剩余数量 = total - sold
    total_cost_jpy REAL,              -- 总成本（不含税）
    total_tax_jpy REAL,               -- 总税额
    average_cost_per_unit REAL,       -- 平均单位成本
    last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

### 3.3 索引

```sql
CREATE INDEX IF NOT EXISTS idx_inventory_sku ON inventory(item_sku);
CREATE INDEX IF NOT EXISTS idx_pol_allocated ON purchase_order_links(allocated_qty);
```

---

## 4. FIFO 分配算法

### 4.1 伪代码

```python
def allocate_fifo(ebay_order: dict) -> list[dict]:
    """
    为单个 eBay 订单分配采购成本（FIFO）
    
    参数:
        ebay_order: {order_id, item_title, item_id, quantity, sale_date}
    
    返回:
        allocations: [{purchase_id, allocated_qty, allocated_cost_jpy, allocated_tax_jpy}]
    """
    allocations = []
    remaining_qty = ebay_order['quantity']
    
    # 按采购日期排序，获取所有未完全分配的采购记录
    purchases = fetch("""
        SELECT p.*, 
               COALESCE(SUM(pol.allocated_qty), 0) as already_allocated
        FROM purchases p
        LEFT JOIN purchase_order_links pol ON p.id = pol.purchase_id
        WHERE p.item_sku = ? OR brand_match(p.item_name, ?)
        GROUP BY p.id
        HAVING (p.quantity - already_allocated) > 0
        ORDER BY p.purchase_date ASC
    """, (ebay_order['item_id'], ebay_order['item_title']))
    
    for purchase in purchases:
        if remaining_qty <= 0:
            break
        
        available_qty = purchase['quantity'] - purchase['already_allocated']
        allocate_qty = min(remaining_qty, available_qty)
        
        # 按比例分配成本和税额
        unit_cost = purchase['total_price_jpy'] / purchase['quantity']
        unit_tax = purchase['tax_jpy'] / purchase['quantity']
        
        allocations.append({
            'purchase_id': purchase['id'],
            'allocated_qty': allocate_qty,
            'allocated_cost_jpy': unit_cost * allocate_qty,
            'allocated_tax_jpy': unit_tax * allocate_qty
        })
        
        remaining_qty -= allocate_qty
    
    return allocations
```

### 4.2 更新 purchase_order_links

```python
def save_allocations(order_id: str, allocations: list[dict]):
    """保存 FIFO 分配结果到数据库"""
    for alloc in allocations:
        # 检查是否已存在匹配记录
        existing = fetch_one("""
            SELECT id FROM purchase_order_links
            WHERE purchase_id = ? AND ebay_order_id = ?
        """, (alloc['purchase_id'], order_id))
        
        if existing:
            # 更新现有记录
            execute("""
                UPDATE purchase_order_links
                SET allocated_qty = ?, allocated_cost_jpy = ?, allocated_tax_jpy = ?
                WHERE purchase_id = ? AND ebay_order_id = ?
            """, (alloc['allocated_qty'], alloc['allocated_cost_jpy'], 
                  alloc['allocated_tax_jpy'], alloc['purchase_id'], order_id))
        else:
            # 插入新记录
            insert('purchase_order_links', {
                'purchase_id': alloc['purchase_id'],
                'ebay_order_id': order_id,
                'match_method': 'fifo',
                'confidence': 0.8,  # FIFO 匹配的默认置信度
                'allocated_qty': alloc['allocated_qty'],
                'allocated_cost_jpy': alloc['allocated_cost_jpy'],
                'allocated_tax_jpy': alloc['allocated_tax_jpy']
            })
```

### 4.3 更新 inventory 表

```python
def update_inventory():
    """重建库存表（每次匹配后调用）"""
    # 清空并重建
    execute("DELETE FROM inventory")
    
    # 按 SKU 聚合采购数据
    inventory_data = fetch_all("""
        SELECT 
            p.item_sku,
            p.item_name,
            p.item_name_en,
            SUM(p.quantity) as total_quantity,
            SUM(COALESCE(pol.allocated_qty, 0)) as sold_quantity,
            SUM(p.total_price_jpy) as total_cost_jpy,
            SUM(p.tax_jpy) as total_tax_jpy
        FROM purchases p
        LEFT JOIN purchase_order_links pol ON p.id = pol.purchase_id
        WHERE p.item_sku IS NOT NULL
        GROUP BY p.item_sku
    """)
    
    for item in inventory_data:
        insert('inventory', {
            'id': f"inventory_{item['item_sku']}_{datetime.now().strftime('%Y%m%d')}",
            'item_sku': item['item_sku'],
            'item_name': item['item_name'],
            'item_name_en': item['item_name_en'],
            'total_quantity': item['total_quantity'],
            'sold_quantity': item['sold_quantity'],
            'remaining_quantity': item['total_quantity'] - item['sold_quantity'],
            'total_cost_jpy': item['total_cost_jpy'],
            'total_tax_jpy': item['total_tax_jpy'],
            'average_cost_per_unit': item['total_cost_jpy'] / item['total_quantity'] if item['total_quantity'] > 0 else 0
        })
```

---

## 5. 匹配流程

### 5.1 主流程

```
1. 清空 purchase_order_links 表（或标记为待更新）
2. 对所有 ebay_orders 执行 Layer 1 匹配（锚点精确）
   - 匹配成功 → 写入 links 表，置信度=1.0，跳过后续层级
3. 对未匹配订单执行 Layer 2 匹配（品牌词典）
   - 匹配成功 → 写入 links 表，置信度=0.7~0.95
4. 对仍未匹配订单执行 Layer 3 匹配（日期窗口）
   - 匹配成功 → 写入 links 表，置信度=0.5~0.7
5. 对所有匹配成功的订单执行 FIFO 成本分配
6. 更新 inventory 表
```

### 5.2 验收标准

| 指标 | 目标值 |
|------|--------|
| 采购↔订单匹配覆盖率 | ≥ 40% |
| Layer 1 匹配准确率 | 100% |
| Layer 2 匹配准确率 | ≥ 90% |
| Layer 3 匹配准确率 | ≥ 70% |
| FIFO 成本分配正确率 | 100% |

---

## 6. 实现清单

- [ ] 创建 `matcher/brand_dict.py`
- [ ] 更新 `matcher/purchase_order.py` 实现三层匹配
- [ ] 创建 `db/migrate.py` 添加新字段和表
- [ ] 实现 `allocate_fifo()` 函数
- [ ] 实现 `update_inventory()` 函数
- [ ] 更新 `generator/spreadsheet.py` 读取 allocated 字段
- [ ] 添加单元测试
- [ ] 运行回归测试

---

## 7. 备注

- 本规格书取代 v1 版本（`matcher_purchase_date_window_spec.md`）
- FIFO 分配确保同一商品多次采购时，按采购时间顺序分配成本
- inventory 表用于快速查询库存状态，支持未来扩展
