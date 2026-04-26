# 财务语义文档(eBay-MS Finance Semantics)

**版本**:v1.1,2026-04-26
**对应代码基线**:Day 31-C(在 5eab8c9 之上)

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

当前代码实际会写入的 Transaction 类型(Day 31-C 为准):

| type | sku | amount_jpy 符号 | 含义 | 采集自 eBay API 字段 | 当前实现 |
|------|-----|---------------|------|---------------------|---------|
| **SALE** | 非 NULL | **+** | 商品售价(不含税不含运费) | `lineItems[i].lineItemCost.value` | ✅ 已实装 |
| **FEE** | NULL | **−** | 平台费合计(各种子费混在一起) | `lineItems[i].itemTxSummaries[j]` where `transactionType=='FEE'` | ✅ 已实装,**但不区分子类** |
| **SHIPPING** | NULL | **+** | 买家支付的运费(卖家收入) | `fulfillmentHrefs[0].shippingCost.value` | ✅ 已实装 |
| **AD_FEE** | NULL | **−** | Promoted Listing 广告费 | `/sell/finances/v1/transaction` 中 `transactionType=NON_SALE_CHARGE` & `feeType=AD_FEE`,或 `itemTxSummaries[j]` 中 `feeType=AD_FEE` | ✅ 已实装(Day 31-B) |
| **SALE_TAX** | NULL | **+** | 销售税(代收代付,转给税局,**不进任何聚合**) | 订单级 `ebayCollectAndRemitTaxes[]` | ✅ 已实装(Day 31-B) |
| **REFUND** | 视情况 | **−** | 退款 | 手工或未来扩展 | ⚠️ 模型存在,`OrderSyncService` 未写入 |
| **ADJUSTMENT** | 视情况 | 任意 | 人工调整 | 手工 | ⚠️ 模型存在,无自动采集 |

**Order 表订单级新增字段(Day 31-B 实装)**:

| 字段 | 类型 | 含义 |
|------|------|------|
| `Order.ad_fee_total` | Numeric, nullable | 订单级广告费合计(冗余存,用于守恒校验) |
| `Order.buyer_paid_total` | Numeric, nullable | 买家实际支付总额(`pricingSummary.total + ebayCollectAndRemitTaxes`,**含税**) |

**当前完全未采集的项**(Day 31.5+):

| 项目 | 来源 | 现实状态 | 对毛利的影响 |
|------|------|---------|-------------|
| **物流实际运费 (shipping_actual)** | 非 eBay API,来自 Orange Connex CSV | ❌ 未采集(Day 31.5 引入多源 CSV 导入) | **高估毛利**(运费是实打实的出向) |

**符号规则**(`OrderSyncService` / `TransactionService` 写入时强制):

- SALE.amount_jpy 始终为正(收入)
- FEE.amount_jpy 始终为负(符号化:`amount=float(-fee_amount)`)
- SHIPPING.amount_jpy 始终为正(买家付的,收入侧)
- AD_FEE.amount_jpy 始终为负(同 FEE 符号化,聚合时取绝对值)
- SALE_TAX.amount_jpy 始终为正("买家付的钱路过",代收代付,**不进任何聚合**)
- REFUND.amount_jpy 为负(退款,冲销收入)
- ADJUSTMENT 不限符号

---

## 4. 毛利润公式(2 个版本)

### 4a. 严谨的完整公式(目标态,现阶段无法计算)

```
净利润 = Σ SALE.amount_jpy                    ← 商品售价收入(+)
       + Σ SHIPPING.amount_jpy                ← 买家付的运费(+,收入侧)
       + Σ FEE.amount_jpy                     ← 平台费(−,已符号化)
       + Σ AD_FEE.amount_jpy                  ← Promoted Listing 广告费(−,已符号化,Day 31-B 起采集)
       + Σ REFUND.amount_jpy                  ← 退款(−,冲销收入)
       − Σ SALE.total_cost                    ← 进货成本 COGS(+)
       − Σ SHIPPING_ACTUAL.amount_jpy         ← ❌ 待采集(物流实际运费,Orange Connex 侧,Day 31.5)
```

注:SALE_TAX **不在公式中**——本质是代收代付,且 `total_revenue` 基于 lineItemCost(不含税),详见 §4c。

标注 ❌ 的一项在当前系统里**值恒为 0**(因为没有对应 Transaction 记录)。当前毛利仍**系统性高估**实际利润,但偏差幅度比 Day 28 时小很多(广告费已扣)。

### 4b. 现阶段可用公式(Day 29 → Day 31-C Dashboard 实际使用)

```
total_revenue   = Σ amount_jpy where type IN (SALE, SHIPPING, REFUND)
                  AND amount_jpy IS NOT NULL

total_cost      = Σ total_cost where type = SALE AND total_cost IS NOT NULL

total_fee       = Σ |amount_jpy| where type = FEE AND amount_jpy IS NOT NULL
                  (取绝对值;对外展示为"正数的费用支出")

total_ad_fee    = Σ |amount_jpy| where type = AD_FEE AND amount_jpy IS NOT NULL
                  (取绝对值;Day 31-C 起独立展示为 "Promoted Listing 费用")

gross_profit    = total_revenue − total_cost − total_fee − total_ad_fee

gross_margin    = gross_profit / total_revenue   (total_revenue > 0 时)
```

**Dashboard 必须显式声明**(在 CLI 输出和任何报表里):

> ⚠️ 当前成本只含 COGS、平台费、广告费,未含:物流实际运费。
> 毛利润数值仍然偏高(但比 Day 28 时小很多,已扣广告费)。
> 待 Day 31.5 多源 CSV 导入采集 shipping_actual 后,数值会进一步趋真实。

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
7. `Σ Transaction.AD_FEE.amount == -Order.ad_fee_total`(对 `ad_fee_total` 非 NULL 的订单,Day 31-B 起)
8. `Σ Transaction.SALE_TAX.amount >= 0`(销售税总和应非负,Day 31-B 起)
9. `Order.buyer_paid_total ≈ Σ SALE.amount + Σ SHIPPING.amount + Σ SALE_TAX.amount`(原币 USD,容差 1e-2,Day 31-B 起)

---

## 7. 未来工作清单(路线图)

| 任务 | 目标版本 | 说明 / 状态 |
|------|---------|------|
| 扩 `OrderSyncService._extract_fee_from_order` 分解 FEE 子类 | Day 31.5+ | 分开记 FINAL_VALUE / INTERNATIONAL / REGULATORY;FEE 记录可加 `category` 区分 |
| 采集广告费 AD_FEE | Day 31-B | ✅ **已完成**(commit `1b51b86`) |
| 采集销售税 SALE_TAX | Day 31-B | ✅ **已完成**(commit `1b51b86`) |
| 采集 `pricingSummary.total` → `Order.buyer_paid_total` | Day 31-B | ✅ **已完成**(commit `1b51b86`) |
| Dashboard / Breakdown 公式纳入 AD_FEE | Day 31-C | ✅ **已完成**(本次) |
| 引入 `shipping_actual` 字段和 Transaction 类型 | Day 31.5 | 来源 Orange Connex CSV,非 eBay API,多源导入 |
| Dashboard 显示精确毛利(含所有费用) | Day 31.5 后 | 当前公式无需再改,只要数据进 Transaction 表,聚合自动正确 |
| `order_analyzer.py`(单笔订单盈亏分析) | Day 31.5+ | 待 shipping_actual 采集就位后再做 |
| REFUND 自动采集 | 未排期 | 需要在 order status 变化时或通过 Finances API 触发 |

---

## 8. 约定与记号

- 所有 "费用"在公式里**以有符号值出现**(FEE/REFUND 是负的),Dashboard 在展示层取绝对值转正。**代码层不要混淆**:聚合用符号,展示取绝对值。
- 所有金额字段类型:`Numeric(12, 2)` 或 `Numeric(14, 4)`(JPY 精度)。不要用 `float` 做中间计算,Decimal 全程保留。
- `Transaction.profit` 和 `Transaction.margin` 字段只在 SALE 上有值,且只算了 COGS,**不能直接 SUM 当作毛利润**。任何聚合都要从原始 `amount_jpy` / `total_cost` 重新算。
