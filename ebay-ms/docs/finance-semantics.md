# 财务语义文档(eBay-MS Finance Semantics)

**版本**:v1.0,2026-04-22
**对应代码基线**:Day 28(HEAD = `7c9b44b`)

本文档固化 eBay-MS 项目的财务核算语义。任何涉及金额/利润计算的代码和测试,必须以本文档为准。

---

## 1. 本位币与币种

- **本位币 = JPY**。所有汇总、报表、看板、对比都以 JPY 为单位。
- **原币**(通常 USD) 保留在 `Transaction.amount` / `Transaction.currency`,用于审计追溯,**不参与任何聚合计算**。
- **换算规则**:`Transaction.amount_jpy = amount × Transaction.exchange_rate`。`exchange_rate` 是"把 Transaction.amount(原币)换成 JPY 所用的那个汇率",日期以 `Order.order_date.date()` 为准(sync 时确定,rebuild 时按最新 CSV 再算)。
- **`amount_jpy IS NULL`** 意味着汇率缺失(当日及 fallback 7 天内都没有汇率记录),这条流水**不计入任何聚合**,但需要在结果里单独报告 `uncovered_count`。

---

## 2. eBay 订单资金流(业务方视角)

```
       买家支付 (pricingSummary.total)
               │
       ┌───────┴──────────────────────────────────────┐
       │                                              │
   ┌───▼────────────────┐                   ┌────────▼─────────┐
   │ 我们实际收到        │                   │ eBay 扣下 / 转付  │
   │ (lands on our bank) │                   │ (never hits us)   │
   └────────────────────┘                   └──────────────────┘
       ▲                                              │
       │ = buyer total                                ├─► 平台费 (FEE):
       │   - 平台费                                    │     final_value_fee
       │   - 广告费                                    │     international_fee
       │   - 税费                                      │     regulatory_fee ...
       │                                              ├─► 广告费 (AD_FEE,
                                                      │     Promoted Listings)
                                                      └─► 销售税 (SALE_TAX,
                                                            转给税局)
```

### 关键业务事实

1. **买家付的运费 = 我们的收入**。买家支付的运费会进入我们的账户。
2. **我们付给物流商的实际运费** = 我们的成本。**但这部分数据不在 eBay API 里,由另一个物流平台(Orange Connex)记录**。本系统目前不采集这个字段 —— `shipping_actual` 字段和 Transaction 类型暂缺,规划 Day 31 单笔盈亏分析时引入。
3. **平台费、广告费、税费 — 三者都是从订单销售金额中扣除**。它们不会到卖家账户,但都是订单的资金出向。从卖家利润表看,它们都是"收入侧的减项"。

---

## 3. Transaction 类型与语义

当前代码实际会写入的 Transaction 类型(Day 28 为准):

| type | sku | amount_jpy 符号 | 含义 | 采集自 eBay API 字段 | 当前实现 |
|------|-----|---------------|------|---------------------|---------|
| **SALE** | 非 NULL | **+** | 商品售价(不含税不含运费) | `lineItems[i].lineItemCost.value` | ✅ 已实装 |
| **FEE** | NULL | **−** | 平台费合计(各种子费混在一起) | `lineItems[i].itemTxSummaries[j]` where `transactionType=='FEE'` | ✅ 已实装,**但不区分子类** |
| **SHIPPING** | NULL | **+** | 买家支付的运费(卖家收入) | `fulfillmentHrefs[0].shippingCost.value` | ✅ 已实装 |
| **REFUND** | 视情况 | **−** | 退款 | 手工或未来扩展 | ⚠️ 模型存在,`OrderSyncService` 未写入 |
| **ADJUSTMENT** | 视情况 | 任意 | 人工调整 | 手工 | ⚠️ 模型存在,无自动采集 |

**不在 Transaction 表里、目前完全未采集的项**(重要!):

| 项目 | 来源 eBay API 字段 | 现实状态 | 对毛利的影响 |
|------|------------------|---------|-------------|
| **广告费 (AD_FEE)** | `itemTxSummaries[j]` where `transactionType=='NON_SALE_CHARGE'` 且 `feeType=='AD_FEE'`,或 `/sell/finances/v1/transactions?transactionType=NON_SALE_CHARGE` | ❌ 未采集 | **高估毛利**(最近 Ariel 很多订单有推广,金额可观) |
| **销售税 (SALE_TAX)** | `itemTxSummaries[j]` where `transactionType=='SALE_TAX'`,或订单级 `taxCollectedByEbay[]` | ❌ 未采集 | **高估毛利**(税费各地不同,平均约 8-10% 订单额) |
| **买家实际支付总额** | 订单级 `pricingSummary.total.value` | ❌ 未采集 | 无法对账 "买家付的 = 商品 + 运费 + 税" |
| **物流实际运费 (shipping_actual)** | 非 eBay API,来自 Orange Connex | ❌ 未采集 | **高估毛利**(运费是实打实的出向) |

**符号规则**(`OrderSyncService` / `TransactionService` 写入时强制):

- SALE.amount_jpy 始终为正(收入)
- FEE.amount_jpy 始终为负(符号化:`amount=float(-fee_amount)`)
- SHIPPING.amount_jpy 始终为正(买家付的,收入侧)
- REFUND.amount_jpy 为负(退款,冲销收入)
- ADJUSTMENT 不限符号

---

## 4. 毛利润公式(2 个版本)

### 4a. 严谨的完整公式(目标态,现阶段无法计算)

```
净利润 = Σ SALE.amount_jpy                    ← 商品售价收入(+)
       + Σ SHIPPING.amount_jpy                ← 买家付的运费(+,收入侧)
       + Σ FEE.amount_jpy                     ← 平台费(−,已符号化)
       + Σ REFUND.amount_jpy                  ← 退款(−,冲销收入)
       − Σ SALE.total_cost                    ← 进货成本 COGS(+)
       − Σ SHIPPING_ACTUAL.amount_jpy         ← ❌ 待采集(物流实际运费,Orange Connex 侧)
       − Σ AD_FEE.amount_jpy                  ← ❌ 待采集(广告费)
       − Σ SALE_TAX.amount_jpy                ← ❌ 待采集(销售税,本质转付给税局)
```

标注 ❌ 的三项在当前系统里**值恒为 0**(因为没有对应 Transaction 记录)。任何使用此公式计算的数字都会**系统性高估毛利**。

### 4b. 现阶段可用公式(Day 29 Dashboard 实际使用)

```
total_revenue   = Σ amount_jpy where type IN (SALE, SHIPPING, REFUND)
                  AND amount_jpy IS NOT NULL

total_cost      = Σ total_cost where type = SALE AND total_cost IS NOT NULL

total_fee       = Σ |amount_jpy| where type = FEE AND amount_jpy IS NOT NULL
                  (取绝对值;对外展示为"正数的费用支出")

gross_profit    = total_revenue − total_cost − total_fee

gross_margin    = gross_profit / total_revenue   (total_revenue > 0 时)
```

**Dashboard 必须显式声明**(在 CLI 输出和任何报表里):

> ⚠️ 当前成本只含 COGS,未含:广告费、销售税、物流实际运费。
> 毛利润数值系统性偏高,不可直接作经营决策依据。
> 待 Day 31 补齐采集后,数值会趋真实。

### 4c. 税费是否算"利润减项"?

税费(SALE_TAX)本质是**代收代付**:买家付给 eBay,eBay 转给税局,不经过卖家。严格说:

- **如果 `total_revenue` 包含税费 → 净利润公式应减去税费**(保持零影响)
- **如果 `total_revenue` 不包含税费 → 净利润公式不用减税费**

**当前系统语义**:`SALE.amount_jpy = lineItemCost.value × qty × rate`,`lineItemCost.value` 是**不含税商品价**,所以 `total_revenue` **不包含税费**。因此严格的正确公式**不需要减税费**(已经从收入里剥离)。

但买家视角,税费是订单金额的一部分。如果未来要对买家支付的总额对账,就需要采集 `pricingSummary.total`,并在那一侧的公式里减掉税费。

**这是一个容易混淆的点,务必按本节的"当前系统语义"口径算账**:
- `total_revenue` 里**不含税**(因为 SALE 基于 lineItemCost)
- 所以毛利公式**不再减税**(税已经不在 revenue 里)
- 税费的采集(Day 31 扩)主要用途是:对账 `pricingSummary.total = SALE + SHIPPING + TAX`,检验数据完整性,不是为了减去

---

## 5. 货币污染历史(已修)

Day 27 之前,`OrderSyncService._write_sale_transaction` 的 profit 公式:

```python
profit = float(sale_amount)  -  float(unit_cost * quantity)
#        ↑ USD(lineItemCost)   ↑ JPY(Product.cost_price)
```

直接用 USD 减 JPY,整个 profit / margin 字段无业务意义。

Day 28(commit `7c9b44b`)修复:

```python
rate_used = get_exchange_rate(sess, "USD", "JPY", order_date.date())
amount_jpy = Decimal(sale_amount) × rate_used
profit_jpy = amount_jpy − (unit_cost × quantity)   # 两边都 JPY
margin = profit_jpy / amount_jpy
```

---

## 6. 每笔订单的守恒不变式(测试必须守住)

对每个 `Order.ebay_order_id`:

1. `Σ Transaction.SALE.amount for this order == Order.sale_price`(原币 USD 守恒)
2. `Σ Transaction.SALE.amount_jpy for this order ≈ Order.sale_price × exchange_rate`(容差 1e-2)
3. `Σ Transaction.FEE.amount == -Order.ebay_fee`(负数守恒)
4. `Σ Transaction.SHIPPING.amount == Order.shipping_cost`
5. `count(SALE) == count(OrderItem)`(SALE per-SKU,不能合并)
6. `count(FEE) ≤ 1` 且 `count(SHIPPING) ≤ 1`(FEE/SHIPPING per-order,不能重复)

---

## 7. 未来工作清单(路线图)

| 任务 | 目标版本 | 说明 |
|------|---------|------|
| 扩 `OrderSyncService._extract_fee_from_order` 分解 FEE 子类 | Day 31 | 分开记 FINAL_VALUE / INTERNATIONAL / REGULATORY;FEE 记录可加 `category` 区分 |
| 采集广告费 AD_FEE | Day 31 | 需要调 `/sell/finances/v1/transactions?transactionType=NON_SALE_CHARGE` |
| 采集销售税 SALE_TAX | Day 31 | 用 `itemTxSummaries[type=SALE_TAX]` 或订单级 `taxCollectedByEbay` |
| 采集 `pricingSummary.total` | Day 31 | 用于对账,存 `Order.buyer_paid_total`(新字段) |
| 引入 `shipping_actual` 字段和 Transaction 类型 | Day 31 | 来源 Orange Connex CSV,非 eBay API |
| Dashboard 显示精确毛利(含所有费用) | 采集全部就位后 | Day 29 的 dashboard 公式不用改,只要数据进了 Transaction 表,聚合就自动正确 |
| REFUND 自动采集 | 未排期 | 需要在 order status 变化时或通过 Finances API 触发 |

---

## 8. 约定与记号

- 所有 "费用"在公式里**以有符号值出现**(FEE/REFUND 是负的),Dashboard 在展示层取绝对值转正。**代码层不要混淆**:聚合用符号,展示取绝对值。
- 所有金额字段类型:`Numeric(12, 2)` 或 `Numeric(14, 4)`(JPY 精度)。不要用 `float` 做中间计算,Decimal 全程保留。
- `Transaction.profit` 和 `Transaction.margin` 字段只在 SALE 上有值,且只算了 COGS,**不能直接 SUM 当作毛利润**。任何聚合都要从原始 `amount_jpy` / `total_cost` 重新算。
