# eBay Listing API 发布系统

> 完整的 Listing 发布流程：读取商品表 → 生成内容 → 预审核 → 上架 → 回写结果

## 系统架构

```
Step 1: 读取商品表（Google Drive）
Step 2: 生成 Listing 内容 → 上传 Google Drive 审核文件夹
Step 3: 预审核页面（review_web.py）→ 调整参数 → 确认发布
Step 4: eBay API 上架 → 回写结果到源表
```

## 文档

- [系统架构 v1.0](./ARCHITECTURE.md) — 完整架构说明
- [GitHub Issues](https://github.com/aaariel0506-debug/ebay-project/issues?q=is%3Aissue) — 开发任务列表

## 开发看板

**Milestone:** [v1.0 - Listing 发布系统](https://github.com/aaariel0506-debug/ebay-project/milestones)

## 当前状态

| Step | 状态 | 说明 |
|------|------|------|
| Step 1: 读取商品表 | ✅ 完成 | 从 Google Drive 读取商品数据（需填商品） |
| Step 2: 生成内容 | 🔨 开发中 | fetch_product.py, generate_content.py |
| Step 3: 预审核页面 | 🔨 开发中 | review_web.py 重构 |
| Step 4: 上架回写 | 🔨 开发中 | create_listing.py + 回写逻辑 |

## 快速开始

```bash
# 本地配置
cd src/listing-system
python3 scripts/make_config.py        # 生成 config.json
python3 review_web.py                # 启动预审核页面 http://localhost:8080

# GitHub Actions（自动）
# push 代码到 main 分支自动触发 workflow
```

## 目录结构

```
src/listing-system/
├── main.py                    # 流程总控
├── create_listing.py          # eBay API 发布
├── review_web.py              # 预审核页面（Flask）
├── upload_drive.py            # Google Drive 上传
├── scripts/
│   ├── make_config.py        # 生成 config.json
│   ├── fetch_product.py       # 从 EC URL 抓取商品信息 [待开发]
│   ├── fetch_upc.py          # 从最安値查询 UPC [待开发]
│   └── generate_content.py    # 生成 Listing 内容 [待开发]
└── docs/
    ├── ARCHITECTURE.md        # 架构文档
    └── eBay API Listing V1.0   # 商品数据表
```

## 环境变量（Secrets）

GitHub Actions Secrets:

| Name | 说明 |
|------|------|
| `EBAY_APP_ID` | eBay Application ID |
| `EBAY_APP_SECRET` | eBay Application Secret |
| `EBAY_USER_TOKEN` | User Access Token（长期有效）|
| `EBAY_REFRESH_TOKEN` | Refresh Token（续期用）|
| `MATON_API_KEY` | Google Drive Maton API Key |

## Google Drive 结构

```
08 ebay-project/ebay listing API/
├── eBay API Listing V1.0          ← 商品源数据表
├── eBay Description Template       ← 描述模板
├── input/                          ← 原始文件入口
└── [SKU]_[商品名]/                ← 每个商品一个审核文件夹
    ├── listing_content.html
    ├── review_data.json
    └── images/
```

## eBay API 分类参考

| 商品类型 | Category ID |
|----------|-------------|
| Tarot Cards / Oracle Cards | 35837 |
| Hobonichi Products | 45112 |
| Default | 262302 |
