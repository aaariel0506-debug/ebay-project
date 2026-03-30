# eBay Tax System — eBay 店铺税务报表自动化系统

> 将多源采购数据、eBay 订单数据、快递数据自动匹配聚合，生成结构化税务报表，并按订单整理凭证文件夹。

---

## 系统架构

```
[多源输入] → [Ingestion] → [SQLite DB] → [Matching引擎] → [Generator] → [报表 + 文件夹]
```

详细架构见 [`docs/architecture.md`](docs/architecture.md)

---

## 快速开始

### 环境要求
- Python 3.11+
- Tesseract OCR（日文包）
- Playwright（截图功能）

### 安装

```bash
pip install -r requirements.txt
playwright install chromium
```

### 配置

```bash
cp config.example.yaml config.yaml
# 编辑 config.yaml 填入账号信息
```

### 使用流程

```bash
# 1. 初始化数据库
python main.py init

# 2. 导入所有数据
python main.py ingest --all

# 3. 运行自动匹配
python main.py match

# 4. 手动审核未匹配记录
python main.py review

# 5. 生成报表和文件夹（指定年份）
python main.py generate --year 2025

# 查看匹配统计
python main.py status
```

---

## 输入数据说明

| 数据源 | 格式 | 存放路径 |
|--------|------|----------|
| eBay 订单 | CSV（Seller Hub导出）| `data/inputs/ebay/` |
| CPass 快递 | CSV | `data/inputs/cpass/` |
| 日本亚马逊 | CSV | `data/inputs/amazon_jp/` |
| Hobonichi | CSV/Excel | `data/inputs/hobonichi/` |
| Bandai | CSV/Excel | `data/inputs/bandai/` |
| 线下领收书 | JPG/PNG 照片 | `data/inputs/receipts/` |
| Japan Post 邮件 | .eml 文件 | `data/inputs/japanpost_emails/` |

---

## 输出说明

```
data/outputs/
├── tax_report_2025.xlsx          # 税务报表主文件
└── orders/
    └── eBay_ORDER_001/
        ├── 01_ebay_order_detail.png
        ├── 02_ebay_order_receipt.pdf
        ├── 03_shipping_label.pdf
        ├── 04_cpass_transaction.pdf
        └── 05_japanpost_email.png   # Japan Post适用
```

---

## 项目结构

```
ebay-tax-system/
├── main.py              # CLI 入口
├── config.example.yaml  # 配置模板
├── requirements.txt
├── models/              # Pydantic 数据模型
├── ingest/              # 各平台数据导入模块
├── db/                  # 数据库操作
├── matcher/             # 三方匹配引擎
├── generator/           # 报表与文件夹生成
├── tests/               # 单元测试
└── docs/                # 文档
```

---

## 开发规范

- 架构设计与验收：Claude (Cowork)
- 代码实现：AI Agent
- 每个模块实现前需对照 `docs/specs/` 下对应规格书
- 提交前需通过 `tests/` 下对应测试

---

*Architecture by Claude (Cowork) · Implementation by AI Agent*
