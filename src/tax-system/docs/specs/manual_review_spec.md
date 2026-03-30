# 规格书：手动审核 CLI（review 命令）

**模块**：`main.py` → `review` 命令 + `matcher/manual_review.py`（新建）
**优先级**：Phase 2（2月报税前需要审核未匹配采购）
**作者**：Claude (Cowork)
**版本**：v1.0

---

## 1. 背景

当前 `python main.py review` 输出 `待实现` 占位符。

2月份报税的问题：
- Amazon JP 采购 vs eBay 订单的自动匹配率低（日英商品名差异大）
- 有11条 CPass 记录和一批采购无法自动匹配
- 需要人工逐条确认或排除

---

## 2. CLI 接口

```bash
# 审核所有未匹配记录
python main.py review

# 只审核未匹配快递
python main.py review --type shipment

# 只审核未匹配采购
python main.py review --type purchase

# 跳过置信度高于 threshold 的记录（只看低置信度）
python main.py review --min-confidence 0 --max-confidence 0.85
```

---

## 3. 交互式审核流程

### 3.1 采购审核（purchase 模式）

每次展示一条未匹配或低置信度采购记录，配上最近3条候选 eBay 订单：

```
════════════════════════════════════════════
[采购记录 12/47]
  采购ID   : amazon_jp_250-1234567-8901234_B08XYZABC
  日期     : 2026-02-10
  商品名   : ほぼ日手帳 2026 カバー A6 黒
  ASIN     : B08XYZABC
  单价     : ¥4,200 × 1 = ¥4,200

候选 eBay 订单：
  [1] 03-14197-21396  2026-02-12  Hobonichi Techo 2026 Cover Black  $35.99  (置信度: 0.72)
  [2] 03-14200-55123  2026-02-15  Hobonichi Planner A6 2026  $32.50  (置信度: 0.61)
  [3] 03-14188-90210  2026-02-08  Japanese Planner Notebook Cover  $28.00  (置信度: 0.45)

操作：[1/2/3] 确认匹配  [s] 跳过  [n] 标记无对应订单  [q] 退出
> _
```

### 3.2 快递审核（shipment 模式）

展示未匹配快递，配上候选 eBay 订单：

```
════════════════════════════════════════════
[快递记录 3/11]
  快递ID        : cpass_EE1013088JP
  CPass单号     : EE1013088JP
  发货日期      : 2026-02-13
  运费          : -
  目前状态      : 未匹配

候选 eBay 订单（发货日期 ±5 天内）：
  [1] 03-14197-21396  2026-02-12  跟踪号: EE1013088JP  (精确单号匹配)
  [2] 03-14200-55123  2026-02-14  跟踪号: (空)

操作：[1/2] 确认匹配  [s] 跳过  [n] 标记异常快递  [q] 退出
> _
```

---

## 4. 数据库操作

### 4.1 确认采购匹配

```sql
-- 插入或更新 purchase_order_links
INSERT OR REPLACE INTO purchase_order_links
  (purchase_id, ebay_order_id, match_method, confidence, confirmed_by)
VALUES
  (:purchase_id, :order_id, 'manual', 1.0, 'user');
```

`confirmed_by` 字段需要在 `purchase_order_links` 表中新增（通过 `_migrate()` 自动添加）：
```sql
ALTER TABLE purchase_order_links ADD COLUMN confirmed_by TEXT DEFAULT NULL;
-- 值：'auto' | 'user' | NULL
```

### 4.2 标记无对应订单

```sql
-- 在 purchases 表添加 no_match_reason 列（通过 migrate 添加）
ALTER TABLE purchases ADD COLUMN no_match_reason TEXT DEFAULT NULL;

-- 更新
UPDATE purchases SET no_match_reason = 'no_ebay_order'
WHERE id = :purchase_id;
```

### 4.3 确认快递匹配

```sql
UPDATE shipments
SET ebay_order_id = :order_id,
    match_method = 'manual',
    confirmed_by = 'user'
WHERE id = :shipment_id;
```

`match_method` 和 `confirmed_by` 需对 shipments 表做同样迁移。

---

## 5. 进度保存

审核中途按 `q` 退出后，下次运行自动从断点继续（跳过已审核记录）。
判断逻辑：跳过所有 `confirmed_by = 'user'` 或 `no_match_reason IS NOT NULL` 的记录。

---

## 6. 审核完成汇总

```
════════════════════════════════════════════
审核完成！
  手动确认匹配：18 条
  标记无对应订单：5 条
  跳过（待后续处理）：24 条

运行 `python main.py status` 查看最新匹配统计。
```

---

## 7. 新建文件：`matcher/manual_review.py`

```python
class ManualReviewer:
    def __init__(self, review_type: str, min_confidence: float, max_confidence: float): ...
    def run(self) -> dict: ...  # 返回 {'confirmed': int, 'skipped': int, 'no_match': int}
    def _get_unmatched_purchases(self) -> list[dict]: ...
    def _get_candidates_for_purchase(self, purchase: dict) -> list[dict]: ...
    def _get_unmatched_shipments(self) -> list[dict]: ...
    def _get_candidates_for_shipment(self, shipment: dict) -> list[dict]: ...
    def _confirm_purchase_match(self, purchase_id: str, order_id: str): ...
    def _confirm_shipment_match(self, shipment_id: str, order_id: str): ...
    def _mark_no_match(self, record_type: str, record_id: str): ...
```

---

## 8. main.py 更新

```python
@click.command()
@click.option("--type", "review_type", type=click.Choice(["purchase", "shipment", "all"]),
              default="all", show_default=True, help="审核类型")
@click.option("--min-confidence", type=float, default=0.0, help="最低置信度过滤")
@click.option("--max-confidence", type=float, default=1.0, help="最高置信度过滤")
def review(review_type, min_confidence, max_confidence):
    """手动审核未匹配或低置信度记录"""
    from matcher.manual_review import ManualReviewer
    reviewer = ManualReviewer(review_type, min_confidence, max_confidence)
    result = reviewer.run()
    console.print(f"[green]✓[/green] 审核完成：确认 {result['confirmed']}，跳过 {result['skipped']}，无匹配 {result['no_match']}")
```

---

## 9. 测试要求

新建 `tests/test_manual_review.py`：

```python
def test_reviewer_loads_unmatched(mock_db):
    """能正确加载未匹配记录"""
    pass

def test_confirm_match_updates_db(mock_db):
    """确认匹配后数据库正确更新"""
    pass

def test_mark_no_match_updates_db(mock_db):
    """标记无匹配后设置 no_match_reason"""
    pass
```

---

## 10. 验收标准

- [ ] `python main.py review` 展示未匹配采购和快递，提供交互式操作
- [ ] 输入 `1/2/3` 确认匹配后 `purchase_order_links` / `shipments` 数据库正确更新
- [ ] 输入 `n` 后对应记录标记 `no_match_reason`
- [ ] 输入 `q` 退出后下次运行从断点继续
- [ ] `--type shipment` 只展示快递未匹配
- [ ] `--type purchase` 只展示采购未匹配
- [ ] 所有新增测试通过
