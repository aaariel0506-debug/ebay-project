# 线下库存系统文档

> Phase 4 交付物 — 2026-04-16 完成

---

## 模块结构

```
modules/inventory_offline/
├── __init__.py                    # 导出 OfflineInventoryService
├── offline_inventory_service.py   # 核心服务（入库/出库/退货/库存查询）
├── stocktake_service.py           # 库存盘点服务
├── reporter.py                    # 库存报表生成器（Day 23）
└── ...
```

---

## 核心功能

### 1. 入库管理

**CLI**
```bash
# 创建入库单
python main.py inventory offline inbound-create --supplier "供应商 A" --file items.csv

# 到货确认
python main.py inventory offline inbound-confirm --receipt-id 1 --file received.csv

# 列出入库单
python main.py inventory offline inbound-list --status pending
```

**API**
```python
from modules.inventory_offline import OfflineInventoryService

svc = OfflineInventoryService()
receipt = svc.create_receipt(supplier="供应商 A", items=[...])
svc.confirm_inbound(receipt_id=receipt["receipt_id"], received_items=[...])
```

### 2. 出库管理

**CLI**
```bash
# 出库
python main.py inventory offline outbound --sku TEST-001 --quantity 3 --order ORDER-001

# 退货
python main.py inventory offline return-in --sku TEST-001 --quantity 1 --order ORDER-001

# 查询出库记录
python main.py inventory offline outbound-list --sku TEST-001 --date-from 2026-04-01
```

**API**
```python
svc.outbound(sku="TEST-001", quantity=3, related_order="ORDER-001")
svc.return_inventory(sku="TEST-001", quantity=1, related_order="ORDER-001")
```

### 3. 库存查询

**CLI**
```bash
# 单 SKU 库存
python main.py inventory offline stock TEST-001

# 全量库存快照
python main.py inventory offline stock-all --limit 200
```

**API**
```python
svc.get_stock(sku="TEST-001")  # {"available_quantity": 7, "locations": {"A-1": 5, "B-2": 2}}
svc.get_all_stock(limit=200)   # list[dict]
```

### 4. 库存盘点

**CLI**
```bash
# 开始盘点
python main.py inventory offline stocktake-start --skus TEST-001,TEST-002 --operator 张三

# 录入实点数量
python main.py inventory offline stocktake-record --id 1 --file counts.csv

# 结束盘点
python main.py inventory offline stocktake-finish --id 1

# 查询盘点单
python main.py inventory offline stocktake-list --status in_progress
```

**API**
```python
svc.start_stocktake(skus=["TEST-001"], operator="张三")
svc.record_count(stocktake_id=1, counts={"TEST-001": 8})
svc.finish_stocktake(stocktake_id=1)
```

### 5. 库存报表（Day 23）

**CLI**
```bash
# 完整报表（快照 + 出入库明细）
python main.py inventory offline report

# 只导出快照
python main.py inventory offline report --type snapshot -o snapshot.xlsx

# 只导出明细（指定日期范围）
python main.py inventory offline report --type movements \
  --start-date 2026-04-01 --end-date 2026-04-30 \
  --sku TEST-001
```

**报表内容**
- 快照 Excel：SKU / 商品名称 / 可用数量 / 位置分布 / 进货价 / 库存金额 / 最后入库 / 最后出库
- 明细 Excel：时间 / 类型 / SKU / 数量 / 单件成本 / 总成本 / 订单号 / 操作人 / 备注
- 颜色编码：IN 绿 / OUT 红 / ADJUST 黄 / RETURN 蓝

---

## 事件总线集成

### 发布的事件

| 事件类型 | 触发时机 | payload 字段 |
|---------|---------|-------------|
| `STOCK_OUT` | 出库成功 | sku, quantity, related_order, cost_price, operator, occurred_at |
| `STOCK_RETURN` | 退货成功 | sku, quantity, related_order, operator |
| `STOCKTAKE_FINISHED` | 盘点结束 | stocktake_id, total_difference, adjustment_count |

### 监听的事件

| 事件类型 | 处理器 | 功能 |
|---------|-------|------|
| `STOCK_OUT` | `handle_stock_out()` | 自动扣减 eBay 在线库存（防重复） |

---

## 技术要点

### 库存计算公式

```
available = Σ(IN) + Σ(RETURN) + Σ(ADJUST) - Σ(OUT)
```

### 位置分布计算

```sql
CASE WHEN type = 'out' THEN -quantity
     ELSE quantity
END
```

**注意**：ADJUST 本身带符号存储，不翻符号。

### 防重复扣减

```python
# 查 event_log 中是否有同 related_order 的 DONE STOCK_OUT
dup = sess.query(EventLog).filter(
    EventLog.event_type == "STOCK_OUT",
    EventLog.status == EventStatus.DONE,
).all()
for ev in dup:
    if ev.payload.get("related_order") == related_order:
        return  # 跳过
```

---

## 测试覆盖率

| 模块 | 测试文件 | 测试数 |
|------|---------|-------|
| OfflineInventoryService | test_offline_inventory_service.py | 18 |
| StocktakeService | test_stocktake_service.py | 12 |
| InventoryReporter | test_inventory_reporter.py | 8 |
| Phase 3 DB 集成 | test_*_db.py | 9 |

---

## Git Tag

```bash
git tag v0.4.0-inventory-offline
git push origin --tags
```

---

*Last updated: 2026-04-16*
