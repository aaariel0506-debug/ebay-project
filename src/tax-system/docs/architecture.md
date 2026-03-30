# 系统架构文档

详细架构请参见项目根目录下的完整架构设计文件，或联系架构设计方（Claude Cowork）获取最新版本。

## 模块规格书索引

实现各模块前，请先阅读对应规格书：

| 模块 | 规格书 | 优先级 | 状态 |
|------|--------|--------|------|
| db/schema + db.py | specs/db_spec.md | Phase 1 | ✅ 已实现 |
| ingest/ebay_orders.py | specs/ingest_ebay_spec.md | Phase 1 | ✅ 已实现 |
| ingest/cpass.py | specs/ingest_cpass_spec.md | Phase 1 | ✅ 已实现 |
| matcher/order_shipment.py | specs/matcher_spec.md | Phase 1 | ✅ 已实现 |
| generator/spreadsheet.py | specs/generator_spreadsheet_spec.md | Phase 1 | ✅ 已实现 |
| ingest/amazon_jp.py | specs/ingest_amazon_jp_spec.md | Phase 2 | ✅ 已实现 |
| ingest/hobonichi.py | specs/ingest_hobonichi_spec.md | Phase 2 | ✅ 已实现 |
| ingest/bandai.py | specs/ingest_bandai_spec.md | Phase 2 | ✅ 已实现 |
| ingest/ebay_api.py | specs/ingest_ebay_api_spec.md | Phase 2 | ✅ 已实现 |
| **generate --month 参数** | **specs/generator_month_filter_spec.md** | **Phase 2** | **🔲 待实现** |
| **ingest/exchange_rate.py** | **specs/exchange_rate_spec.md** | **Phase 2** | **🔲 待实现** |
| **matcher/manual_review.py** | **specs/manual_review_spec.md** | **Phase 2** | **🔲 待实现** |
| generator/screenshot.py | specs/generator_screenshot_spec.md | Phase 3 | 🔲 待实现 |
| ingest/offline_receipt.py | specs/ingest_ocr_spec.md | Phase 4 | 🔲 待实现 |
| ingest/japanpost_email.py | specs/ingest_japanpost_spec.md | Phase 5 | 🔲 待实现 |

> 规格书由 Claude (Cowork) 按需生成，请在 Cowork 中请求对应模块的规格书。
>
> **加粗行**为当前 Phase 2（2月报税）待实现项目，openclaw 请按以下顺序实现：
> 1. `specs/exchange_rate_spec.md` → `ingest/exchange_rate.py`（汇率准确性最关键）
> 2. `specs/generator_month_filter_spec.md` → `generate --month` 参数
> 3. `specs/manual_review_spec.md` → `matcher/manual_review.py`

## 协作分工

| 角色 | 负责内容 |
|------|---------|
| **Claude (Cowork)** | 系统设计、规格书编写、验收标准定义、文档维护 |
| **openclaw** | 按规格书实现 Python 代码、编写单元测试、push 到 GitHub |
