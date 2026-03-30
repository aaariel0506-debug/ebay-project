# eBay 店铺运营自动化系统

> 整合 Listing 自动化 + 税务报表一体化的 eBay 店铺运营解决方案

---

## 📋 项目概述

本项目包含两大核心系统：

| 系统 | 功能 | 位置 |
|------|------|------|
| **Listing 自动化系统** | 商品上架、订单同步、图片上传、库存管理 | `src/listing-system/` |
| **税务报表系统** | 多平台数据导入、自动匹配、税务报表生成 | `src/tax-system/` |

---

## 🚀 快速开始

### Listing 系统

```bash
cd src/listing-system
cp config.example.json config.json
# 编辑配置文件填入 API 凭证
python main.py --help
```

### 税务系统

```bash
cd src/tax-system
cp config.example.yaml config.yaml
# 编辑配置文件填入账号信息
python main.py init
python main.py ingest --all
python main.py generate --year 2026
```

---

## 📁 项目结构

```
ebay-project/
├── README.md                    # 本文件
├── docs/                        # 技术文档
│   ├── EBAY_AUTO_PUBLISH_QUICKSTART.md
│   ├── EBAY_ISSUE_ANALYSIS.md
│   ├── EBAY_PERMISSION_SOLUTION.md
│   ├── EBAY_PRODUCTION_SETUP.md
│   ├── EBAY_SANDBOX_WEB_VERIFY.md
│   ├── EBAY_TEST_SUMMARY.md
│   ├── EBAY_TOKEN_KNOWLEDGE.md
│   ├── README_EBAY.md
│   ├── listing-system/          # Listing 系统文档
│   └── tax-system/              # 税务系统文档
├── src/
│   ├── listing-system/          # Listing 自动化系统
│   │   ├── main.py              # CLI 入口
│   │   ├── ebay_client.py       # eBay API 客户端
│   │   ├── listing_creator.py   # Listing 创建
│   │   ├── order_sync.py        # 订单同步
│   │   ├── ebay_image_uploader.py
│   │   ├── config.json
│   │   └── ...
│   └── tax-system/              # 税务报表系统
│       ├── main.py              # CLI 入口
│       ├── ingest/              # 数据导入模块
│       ├── matcher/             # 匹配引擎
│       ├── generator/           # 报表生成
│       ├── db/                  # 数据库操作
│       └── ...
├── scripts/                     # 工具脚本
│   ├── ebay_oauth_get_refresh_token.py
│   ├── ebay_token_manager.py
│   ├── ebay_create_location.py
│   ├── ebay_listing_generator.py
│   └── ...
├── config/                      # 配置文件模板
│   ├── ebay_config.example.json
│   └── ...
└── tests/                       # 测试文件
```

---

## 📚 文档索引

### Listing 系统文档
- [快速开始](docs/EBAY_AUTO_PUBLISH_QUICKSTART.md)
- [生产环境部署](docs/EBAY_PRODUCTION_SETUP.md)
- [权限问题解决方案](docs/EBAY_PERMISSION_SOLUTION.md)
- [Token 管理知识](docs/EBAY_TOKEN_KNOWLEDGE.md)
- [测试总结](docs/EBAY_TEST_SUMMARY.md)

### 税务系统文档
- 架构文档：`src/tax-system/docs/architecture.md`
- 工作流程：`src/tax-system/docs/workflow_feb2026.md`
- 模块规格书：`src/tax-system/docs/specs/`

---

## 🔧 常用命令

### Listing 系统
```bash
# 创建 Listing
python src/listing-system/main.py create --sku "SKU123"

# 同步订单
python src/listing-system/main.py sync-orders

# 上传图片
python src/listing-system/ebay_image_uploader.py --input images/
```

### 税务系统
```bash
# 导入数据
python src/tax-system/main.py ingest --all

# 运行匹配
python src/tax-system/main.py match

# 生成报表
python src/tax-system/main.py generate --year 2026 --month 2

# 查看状态
python src/tax-system/main.py status
```

---

## ⚙️ 环境要求

- Python 3.11+
- Node.js (可选，用于部分工具)
- Tesseract OCR (税务系统，用于日文 OCR)
- Playwright (截图功能)

---

## 📝 配置说明

### Listing 系统配置
编辑 `src/listing-system/config.json`：
```json
{
  "ebay": {
    "appId": "YOUR_APP_ID",
    "certId": "YOUR_CERT_ID",
    "devId": "YOUR_DEV_ID",
    "refreshToken": "YOUR_REFRESH_TOKEN"
  },
  "siteId": 100,
  "marketplaceId": "EBAY_US"
}
```

### 税务系统配置
编辑 `src/tax-system/config.yaml`：
```yaml
ebay:
  seller_id: "YOUR_SELLER_ID"
  output_dir: "./data/outputs"

inputs:
  ebay_csv: "./data/inputs/ebay/"
  cpass_csv: "./data/inputs/cpass/"
  amazon_jp_csv: "./data/inputs/amazon_jp/"
```

---

## 🤝 协作分工

| 角色 | 负责内容 |
|------|---------|
| **架构设计** | 系统设计、规格书编写、验收标准定义 |
| **开发** | 按规格书实现代码、编写测试、维护文档 |
| **运营** | 数据导入、报表生成、日常运维 |

---

## 📊 输出说明

### Listing 系统输出
- Listing 创建日志：`src/listing-system/logs/`
- 上架结果：`src/listing-system/output/`

### 税务系统输出
- 税务报表：`src/tax-system/data/outputs/tax_report_YYYY-MM.xlsx`
- 凭证文件夹：`src/tax-system/data/outputs/orders/`

---

## 🔐 安全提示

- ⚠️ **不要提交**包含真实 API 密钥的配置文件
- ✅ 使用 `.example` 或 `.template` 文件作为模板
- ✅ 真实配置添加到 `.gitignore`

---

## 📞 问题反馈

遇到问题请查看：
1. 对应系统的文档
2. `docs/EBAY_ISSUE_ANALYSIS.md` - 常见问题分析
3. 创建 GitHub Issue

---

*最后更新：2026-03-30*
