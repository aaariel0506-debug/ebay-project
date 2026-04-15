# 线上虚拟库存模块（inventory_online）

Phase 3 核心模块。同步 eBay 在售商品到本地，监控库存状态，检测价格变化，提供补货建议。

## 目录结构

```
modules/inventory_online/
├── sync_service.py       # eBay → 本地全量/增量同步
├── monitor.py            # 库存状态查询 + 缺货预警
├── variant_utils.py      # 变体级别库存解析
├── price_monitor.py      # 进货价变化检测 + 阈值警告
├── restock_advisor.py    # 自动补货建议
└── quantity_adjuster.py  # eBay 库存调整接口
```

## CLI 命令

```bash
# 同步
python main.py inventory online sync         # 从 eBay 拉取所有 listing

# 库存状态
python main.py inventory online status      # 库存概览
python main.py inventory online alert        # 缺货/低库存预警

# 变体级别
python main.py inventory online variant-status   # 各变体库存（按 Size/Color 筛选）

# 进货价监控
python main.py inventory online price-check --file prices.csv   # 批量检查价格变化
python main.py inventory online price-history SKU             # 查看价格历史
python main.py inventory online margin-check --threshold 0.15  # 检查低利润率商品

# 补货建议
python main.py inventory online restock-advice --days 30 --urgent-days 7

# eBay 库存调整
python main.py inventory online adjust --sku 02-2603-0001 --quantity 5
python main.py inventory online adjust --file inventory.csv --dry-run
```

## 核心类

### `SyncService`
- `full_sync()`：全量同步（分页拉取所有 active listing，upsert 到本地）
- `incremental_sync()`：增量同步（只拉取 last_sync_time 后变化的 listing）

### `InventoryMonitor`
- `list_all()`：所有商品库存快照
- `list_out_of_stock()` / `list_low_stock(threshold)`：缺货/低库存
- `check_and_alert(threshold)`：检查并发布 `STOCK_ALERT` 事件
- 变体查询：`list_variant_groups()` / `get_variant_alerts()`

### `PriceMonitor`
- `update_cost_price(sku, new_price)`：更新进货价 + 记录历史 + 触发 PRICE_ALERT
- `batch_update_from_csv(csv_path)`：批量更新
- `get_price_history(sku)`：价格变动历史
- 默认阈值：变化率 10%，最低利润率 15%

### `RestockAdvisor`
- `get_restock_list(lookback_days=30)`：所有 SKU 补货建议
- `print_report()`：格式化报告
- 分类：urgent（< 7 天售罄）/ soon（< 14 天）/ normal

### `QuantityAdjuster`
- `adjust_ebay_quantity(sku, new_quantity)`：单个调整
- `batch_adjust_from_csv(csv_path, dry_run=False)`：批量调整
- 自动写 `audit_log` + 发布 `LISTING_UPDATED` 事件

## 事件

| 事件 | 触发条件 | Payload 关键字段 |
|------|---------|----------------|
| `STOCK_ALERT` | 缺货/低库存/变体缺货 | `alert_type`, `sku`, `quantity` |
| `PRICE_ALERT` | 进货价变化超阈值 | `sku`, `old_price`, `new_price`, `change_rate`, `suggested_action` |
| `LISTING_UPDATED` | eBay 库存调整后 | `sku`, `field=quantity`, `old_value`, `new_value` |

## 数据模型

- `EbayListing`：SKU / ebay_item_id / listing_price / quantity_available / variants JSON
- `SupplierPriceHistory`：sku / price / currency / recorded_at / supplier

## 注意事项

- 同步前请确认 eBay API 权限（Inventory API / Trading API）
- 生产环境同步注意限流：每天最多 ~5000 次 API 调用
- 批量操作建议先用 `--dry-run` 确认
- 价格监控阈值可通过环境变量配置（见 `core/config/settings.py`）
