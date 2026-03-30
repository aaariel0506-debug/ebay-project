# 2026年2月报税工作流程

**作者**：Claude (Cowork)
**更新**：2026-03-13
**目标**：生成2月份完整税务报表 `tax_report_2026-02.xlsx` + 凭证文件夹

---

## 当前状态（截至本文档）

| 项目 | 数量 | 状态 |
|------|------|------|
| eBay 订单 | 105 条 | ✅ 已导入 |
| CPass 快递 | 56 条 | ✅ 已导入，45/56 匹配 |
| Amazon JP 采购 | 59 条 | ✅ 已导入，匹配率低 |
| 汇率 | 硬编码 150 | ⚠️ 等待 openclaw 修复 |
| `generate --month` | 未实现 | ⚠️ 等待 openclaw 实现 |
| 手动审核 | 未实现 | ⚠️ 等待 openclaw 实现 |

---

## 阶段一：等待 openclaw 实现（开发任务）

openclaw 需要按以下顺序完成 3 个功能，详见 `docs/specs/`：

1. **`ingest/exchange_rate.py`**（见 `specs/exchange_rate_spec.md`）
   - Frankfurter API 获取2月逐日 JPY/USD 汇率
   - 报表中每笔订单用成交日实际汇率换算

2. **`generate --month` 参数**（见 `specs/generator_month_filter_spec.md`）
   - 支持 `python main.py generate --year 2026 --month 2`
   - 输出 `tax_report_2026-02.xlsx`

3. **`matcher/manual_review.py`**（见 `specs/manual_review_spec.md`）
   - 交互式审核11条未匹配快递
   - 交互式审核低置信度采购记录

---

## 阶段二：数据补充（openclaw 实现后执行）

openclaw 完成开发并 push 到 GitHub 后，拉取最新代码再执行：

```bash
git pull origin main
pip install -r requirements.txt
```

### 2a. 扩展 eBay API 数据范围（修复11条未匹配快递）

11条 CPass 未匹配的原因是 eBay 订单只导入了2月，而 CPass 文件包含1月数据。
需要把 API 时间范围往前拉到1月：

```bash
python main.py ingest-api --from 2026-01-01 --to 2026-02-28
```

### 2b. 重新运行匹配

```bash
python main.py match
python main.py status
# 目标：快递匹配 56/56，或确认哪些真的无法匹配
```

### 2c. 手动审核（openclaw 实现 review 命令后）

```bash
# 先审核快递（11条，数量少，优先）
python main.py review --type shipment

# 再审核采购（日英商品名差异大，需要逐条判断）
python main.py review --type purchase --max-confidence 0.85
```

---

## 阶段三：生成最终报表

```bash
# 生成2026年2月报表（openclaw 实现 --month 后）
python main.py generate --year 2026 --month 2 --output data/outputs/2026-02/

# 检查输出
ls data/outputs/2026-02/
# 应包含：
#   tax_report_2026-02.xlsx
#   orders_2026-02/  （105个或仅2月订单的文件夹）
```

---

## 阶段四：报表核对要点

拿到 `tax_report_2026-02.xlsx` 后请核对：

| 核对项 | 说明 |
|--------|------|
| 订单数量 | 确认2月份 eBay 订单总数正确 |
| 汇率列 | 每笔订单的 `汇率 (JPY/USD)` 是否为实际市场汇率（约 152~155） |
| 未匹配采购 | 手动审核后应有 `no_match_reason` 标注 |
| 净利润 | 抽查几笔，验算：净利润 = 售价 - 采购成本(USD) - 运费 - eBay费 |
| 汇总行 | 确认报表末尾有合计行 |

---

## 需要准备的原始文件

如有以下2月份文件尚未导入，请提前准备：

| 文件 | 说明 |
|------|------|
| eBay Sales Report CSV | 从 Seller Hub 导出，2月份 |
| CPass XLSX | CPass 平台导出的2月快递记录 |
| Amazon JP CSV | 日本亚马逊2月订单历史 CSV |

放入对应目录：
```
data/inputs/ebay/
data/inputs/cpass/
data/inputs/amazon_jp/
```

---

## 问题排查

**快递还是有未匹配？**
→ 用 `review --type shipment` 逐条手动处理

**采购匹配率还是很低？**
→ 日英商品名差异本身就大，通过 `review --type purchase` 手动确认即可

**汇率还是 150？**
→ 确认 openclaw 已 push exchange_rate.py，并且 `pip install -r requirements.txt` 是最新的

**生成报表时没有 `--month` 选项？**
→ 确认 openclaw 已实现该功能并 push，然后 `git pull` 拉取最新代码
