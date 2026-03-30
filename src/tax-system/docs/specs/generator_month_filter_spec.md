# 规格书：generate 命令月份筛选功能

**模块**：`main.py` + `generator/spreadsheet.py` + `generator/folder_builder.py`
**优先级**：Phase 2（2月报税必须）
**作者**：Claude (Cowork)
**版本**：v1.0

---

## 1. 背景与目标

现有 `generate` 命令只支持 `--year` 参数，输出全年数据。
为了按月生成报表（如仅生成2026年2月份），需增加 `--month` 可选参数。

---

## 2. CLI 接口变更

### 现有接口
```bash
python main.py generate --year 2026 --output path/
```

### 新增接口
```bash
# 生成2月份报表
python main.py generate --year 2026 --month 2 --output path/

# 不带 --month 时保持向后兼容（全年）
python main.py generate --year 2026 --output path/
```

### 参数说明
| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `--year` | int | 是 | 年份，如 2026 |
| `--month` | int | 否 | 月份 1-12；不填则生成全年 |
| `--output` | str | 否 | 输出目录，默认 `data/outputs` |
| `--skip-screenshots` | flag | 否 | 跳过截图 |

### 输出文件名规则
- 全年：`tax_report_2026.xlsx`
- 月份：`tax_report_2026-02.xlsx`（补零对齐）

---

## 3. 数据过滤逻辑

### 3.1 SQL 查询过滤

在以下查询中加入月份条件（`ebay_orders.sale_date` 为 `YYYY-MM-DD` 格式）：

```sql
-- 全年（month=None）
WHERE strftime('%Y', sale_date) = :year

-- 单月（month=2）
WHERE strftime('%Y', sale_date) = :year
  AND strftime('%m', sale_date) = :month_padded
-- :month_padded = '02'（需在 Python 中格式化为两位字符串）
```

### 3.2 影响范围

需要加入月份筛选的位置：
1. `generator/spreadsheet.py` → `generate_report(year, output_path, month=None)` 参数新增
2. `generator/folder_builder.py` → `build_order_folders(year, output_path, month=None)` 参数新增
3. `main.py` → `generate` 命令传递 `month` 给两个 generator

---

## 4. spreadsheet.py 变更规格

### 函数签名
```python
def generate_report(year: int, output_path: str, month: int | None = None) -> None:
```

### 报表标题行
- 全年：`"eBay 税务报表 2026年"`
- 月份：`"eBay 税务报表 2026年02月"`

### 无数据处理
若过滤后订单数为0，生成空报表并打印警告：
```
⚠ 2026年02月 无订单数据，生成空报表
```

---

## 5. folder_builder.py 变更规格

### 函数签名
```python
def build_order_folders(year: int, output_path: str, month: int | None = None) -> int:
```

### 输出目录结构
```
outputs/
├── tax_report_2026-02.xlsx
└── orders_2026-02/          ← 月份模式下子目录加后缀
    ├── 03-14197-21396/
    └── ...
```
- 全年模式：`orders/`（向后兼容，不改变）
- 月份模式：`orders_{year}-{month:02d}/`

---

## 6. 测试要求

在 `tests/test_generator_spreadsheet.py` 增加：

```python
def test_generate_month_filter():
    """月份过滤后只包含该月订单"""
    # 插入1月和2月订单各一条
    # 调用 generate_report(2026, ..., month=2)
    # 验证报表只含2月订单
    pass

def test_generate_month_no_data():
    """无数据时生成空报表不报错"""
    # 调用 generate_report(2026, ..., month=3)（无3月数据）
    # 验证文件生成，内容为空（只有表头）
    pass
```

---

## 7. 验收标准

- [ ] `generate --year 2026 --month 2` 生成 `tax_report_2026-02.xlsx`，只含2月订单
- [ ] `generate --year 2026`（不带 month）行为与现有完全一致
- [ ] 月份为1位数时补零（`--month 2` → `'02'`）
- [ ] 无数据时生成空报表不抛异常
- [ ] 新增测试全部通过
