# 规格书：汇率自动获取（Frankfurter API）

**模块**：`ingest/exchange_rate.py`（新建）+ `generator/spreadsheet.py`
**优先级**：Phase 2（2月报税准确性必须）
**作者**：Claude (Cowork)
**版本**：v1.0

---

## 1. 背景

当前 `generator/spreadsheet.py` 中 JPY→USD 汇率硬编码为 `150`：
```python
EXCHANGE_RATE = 150  # TODO: 接入 API
```

实际汇率每日波动（2026年2月约 152~155 JPY/USD），硬编码会导致采购成本和利润计算偏差。

---

## 2. 目标

- 使用 [Frankfurter API](https://api.frankfurter.app/)（免费、无需 key）获取 JPY/USD 历史汇率
- 报表中每笔订单使用**成交日期当日汇率**进行换算
- 网络不可用时自动 fallback 到 config.yaml 中的备用值

---

## 3. 新建模块：`ingest/exchange_rate.py`

### 3.1 主要函数

```python
def get_rate_jpy_usd(date: str) -> float:
    """
    获取指定日期的 JPY→USD 汇率（1 JPY 换多少 USD）。

    参数：
        date: 'YYYY-MM-DD' 格式日期字符串
    返回：
        float，如 0.00667（约等于 1/150）
    异常：
        网络失败时返回 fallback 值并打印警告，不抛异常
    """
```

```python
def get_usd_per_jpy(date: str) -> float:
    """get_rate_jpy_usd 的别名，语义更清晰"""
```

```python
def batch_get_rates(dates: list[str]) -> dict[str, float]:
    """
    批量获取多个日期的汇率，减少 HTTP 请求次数。

    策略：
    1. 按月份分组，一次请求拉取整月范围
    2. 周末/节假日取最近一个工作日的汇率
    3. 结果缓存到内存（进程生命周期内）

    返回：
        dict，key 为 'YYYY-MM-DD'，value 为 float
    """
```

### 3.2 Frankfurter API 用法

```
# 获取单日汇率（JPY 相对 USD，即 1 USD = ? JPY）
GET https://api.frankfurter.app/2026-02-15?from=USD&to=JPY

# 响应
{
  "amount": 1.0,
  "base": "USD",
  "date": "2026-02-15",
  "rates": {"JPY": 152.87}
}

# 转换：1 JPY = 1/152.87 USD = 0.006541 USD
```

**注意**：API 返回的是 `1 USD = X JPY`，需要取倒数得到 `1 JPY = Y USD`。

```
# 获取区间汇率（用于批量请求）
GET https://api.frankfurter.app/2026-02-01..2026-02-28?from=USD&to=JPY

# 响应
{
  "base": "USD",
  "start_date": "2026-02-01",
  "end_date": "2026-02-28",
  "rates": {
    "2026-02-03": {"JPY": 152.34},
    "2026-02-04": {"JPY": 153.01},
    ...
  }
}
```

### 3.3 周末/节假日处理

Frankfurter 只返回工作日汇率。处理逻辑：

```python
def _find_nearest_rate(date: str, rates_dict: dict) -> float:
    """
    在已获取的 rates_dict 中查找 date 的汇率。
    若 date 不在 dict 中（周末/节假日），向前查找最近的工作日。
    最多回溯 7 天，超过则使用 fallback。
    """
```

### 3.4 缓存

```python
_rate_cache: dict[str, float] = {}  # 模块级缓存

def _cache_key(date: str) -> str:
    return date  # 'YYYY-MM-DD'
```

### 3.5 Fallback 机制

```python
def _get_fallback_rate() -> float:
    """
    从 config.yaml 读取 exchange_rate.fallback_jpy_usd。
    若 config 不存在或字段缺失，返回默认值 1/150。
    """
```

config.yaml 中需新增（`config.example.yaml` 同步更新）：
```yaml
exchange_rate:
  fallback_jpy_usd: 150  # 网络不可用时使用此值（JPY/USD）
  cache_days: 30          # 未来扩展：磁盘缓存天数
```

---

## 4. spreadsheet.py 变更规格

### 4.1 移除硬编码

删除：
```python
EXCHANGE_RATE = 150
```

### 4.2 使用动态汇率

在生成每行数据时：
```python
from ingest.exchange_rate import batch_get_rates

# 先收集所有订单日期
dates = [order['sale_date'] for order in orders]
rates = batch_get_rates(dates)

# 每行换算
for order in orders:
    rate = rates.get(order['sale_date'], 1/150)
    cost_usd = order['total_cost_jpy'] * rate
```

### 4.3 新增列：汇率

在 Excel 报表中新增一列 `汇率 (JPY/USD)`，显示该笔订单使用的汇率，方便核对。

| 列名 | 说明 |
|------|------|
| 汇率 (JPY/USD) | 该订单成交日对应的 1USD = X JPY 值，如 `152.87` |

---

## 5. 错误处理

| 情况 | 处理方式 |
|------|----------|
| 网络超时（>5秒） | 打印 `⚠ 汇率获取失败，使用备用值 150`，继续执行 |
| API 返回非200 | 同上 |
| 日期格式错误 | 打印错误信息 + 使用 fallback |
| 缓存命中 | 直接返回，不发网络请求 |

---

## 6. 测试要求

新建 `tests/test_exchange_rate.py`：

```python
def test_get_rate_returns_float():
    """返回值为合理范围内的 float"""
    # mock requests，返回 {"rates": {"JPY": 150.0}}
    # 验证 get_rate_jpy_usd('2026-02-15') == 1/150.0
    pass

def test_fallback_on_network_error():
    """网络失败时返回 fallback，不抛异常"""
    # mock requests.get 抛出 ConnectionError
    # 验证返回 1/150（默认 fallback）
    pass

def test_weekend_finds_nearest_weekday():
    """周末日期找最近工作日汇率"""
    # date='2026-02-15'(周日) → 应返回 2026-02-14(周五) 的汇率
    pass

def test_batch_get_rates_makes_one_request_per_month():
    """同月多个日期只发一次 API 请求"""
    pass
```

---

## 7. 验收标准

- [ ] `get_rate_jpy_usd('2026-02-15')` 返回合理浮点数（约 1/150 量级）
- [ ] 网络失败时不崩溃，使用 fallback 值
- [ ] 同月日期的汇率只触发一次 API 请求
- [ ] Excel 报表中新增 `汇率 (JPY/USD)` 列
- [ ] `config.example.yaml` 中有 `exchange_rate` 节
- [ ] 所有新增测试通过
