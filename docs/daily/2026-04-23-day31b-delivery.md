# Day 31-B 交付验收文档

**日期**: 2026-04-23
**分支**: HEAD = `ba9a301`
**Brief**: OrderSyncService 扩展采集 AD_FEE / SALE_TAX / buyer_paid_total

---

## 一、交付文件（严格 2 文件）

| 文件 | 变更 | 说明 |
|------|------|------|
| `modules/finance/order_sync_service.py` | +185 行 | 新增 AD_FEE / SALE_TAX 采集 + 写入 + buyer_paid_total |
| `tests/test_order_sync_service.py` | +278 行 | 4 个新测试 + 原有测试 |

**未动文件（确认）**：`dashboard.py` / `breakdown.py` / `finance-semantics.md` / `core/models/*`

---

## 二、功能清单

### 2.1 buyer_paid_total 采集
- **路径**: `order.pricingSummary.total.value`
- **写入**: `Order.buyer_paid_total`（原币，float）
- **字段**: Day 31-A 已加 `Order.buyer_paid_total` column（migration `1f2e3d4c5b6a`）

### 2.2 AD_FEE 采集
- **符号**: 负数（`amount = -ad_fee_amount`）
- **SKU**: `NULL`（订单级，不归属 SKU）
- **幂等**: 每 order_id 至多 1 条 AD_FEE
- **零值**: 金额为 0 不写入
- **采集路径**:
  - **Path A**（主）: `lineItems[].itemTxSummaries[transactionType=NON_SALE_CHARGE, feeType=AD_FEE]`
  - **Path C**（备用）: Finances API `/sell/finances/v1/transactions?orderId={id}&transactionType=NON_SALE_CHARGE`

### 2.3 SALE_TAX 采集
- **符号**: 正数（和 SHIPPING 一样）
- **SKU**: `NULL`（订单级，不归属 SKU）
- **幂等**: 每 order_id 至多 1 条 SALE_TAX
- **零值**: 金额为 0 不写入
- **采集路径**:
  - **Path A**（主）: `lineItems[].itemTxSummaries[transactionType=SALE_TAX]`
  - **Path B**（备用）: `order.taxCollectedByEbay[]`（仅当 Path A 未抓到时）

---

## 三、测试清单

### 3.1 新增 4 个测试

| 测试 | 验证点 |
|------|--------|
| `test_ad_fee_and_sale_tax_written` | 符号/金额/sku=NULL/TransactionType 正确 |
| `test_ad_fee_sale_tax_idempotent` | 重复调用不产生重复 Transaction |
| `test_ad_fee_sale_tax_zero_not_written` | 零值不写入 dummy Transaction |
| `test_sale_tax_from_tax_collected_by_ebay` | Path B 备用路径正常工作 |

### 3.2 全量测试
- **pytest**: 444 passed（440 baseline + 4 new）
- **ruff**: All checks passed
- **Alembic 迁移**: `downgrade` → `upgrade` 往返干净

---

## 四、关键代码变更摘要

### `order_sync_service.py`
1. `_extract_fees_from_order()` — 由旧版单 fee 解析升级为三费用 dict 返回（fee / ad_fee / sale_tax）
2. `_write_ad_fee_transaction()` — 负数符号，sku=NULL，幂等
3. `_write_sale_tax_transaction()` — 正数符号，sku=NULL，幂等
4. `_upsert_order()` — 新增 `buyer_paid_total` 解析 + 调用 `_write_ad_fee_transaction` / `_write_sale_tax_transaction`
5. `OrderStatus` 新增 `REFUNDED` 状态映射

### `tests/test_order_sync_service.py`
- 新增 mock fixtures 模拟 AD_FEE / SALE_TAX 的 API 响应
- 4 个新测试覆盖符号、幂等、零值、备用路径

---

## 五、⚠️ 待确认项（brief §5.3 step 6）

以下两项是 brief 要求交付前用**真实 eBay API 订单 log** 验证的，当前代码使用文档推测值：

| 项目 | 代码当前假设 | 验证状态 |
|------|-------------|----------|
| `NON_SALE_CHARGE.feeType` 的实际字符串 | `"AD_FEE"` | ⏳ 待真实订单验证 |
| `pricingSummary.total.value` 的结构 | `pricingSummary.total.value` | ⏳ 待真实订单验证 |

**建议**：跑一次真实订单同步，打印完整响应 log，确认上述两字段无误。若不一致，补一次小修改（预计 10 分钟以内）。

---

## 六、验收检查清单

- [ ] commit 在 `ba9a301`
- [ ] pytest 全量 444 passed
- [ ] ruff clean
- [ ] 只有 2 个文件变更
- [ ] `dashboard.py` / `breakdown.py` / `core/models/*` 未动
- [ ] AD_FEE 符号为负 ✓
- [ ] SALE_TAX 符号为正 ✓
- [ ] AD_FEE / SALE_TAX 的 sku = NULL ✓
- [ ] 金额为 0 不写 Transaction ✓
- [ ] 幂等性（重复调用不重复写）✓
- [ ] buyer_paid_total 写入 Order.buyer_paid_total ✓
- [ ] §5.3 step 6 验证项（见第五节）
