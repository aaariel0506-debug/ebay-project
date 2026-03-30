# CLAUDE.md - eBay 项目 AI 协作指南

> 本文档帮助 AI 助手（Claude Code）理解项目结构、编码规范和协作流程

---

## 📋 项目概述

**eBay 店铺运营自动化系统** - 包含两大核心模块：
1. **Listing 自动化系统** (`src/listing-system/`) - 商品上架、订单同步
2. **税务报表系统** (`src/tax-system/`) - 数据导入、匹配、报表生成

**技术栈**：Python 3.11+, SQLite, eBay API, OpenPyXL

---

## 🏗️ 项目结构

```
ebay-project/
├── src/listing-system/     # Listing 自动化
│   ├── main.py            # CLI 入口
│   ├── ebay_client.py     # eBay API 客户端
│   ├── listing_creator.py # Listing 创建
│   └── order_sync.py      # 订单同步
├── src/tax-system/         # 税务报表
│   ├── main.py            # CLI 入口
│   ├── ingest/            # 数据导入
│   ├── matcher/           # 匹配引擎
│   └── generator/         # 报表生成
├── scripts/                # 工具脚本
├── docs/                   # 技术文档
└── config/                 # 配置模板
```

---

## 🎯 AI 协作任务类型

### 代码审查
- 检查错误处理是否完善
- 验证 API 调用是否有重试机制
- 确认敏感信息未硬编码

### 功能开发
- 先阅读对应模块的文档
- 遵循现有代码风格
- 编写单元测试

### Bug 修复
- 复现问题
- 定位根因
- 修复后添加回归测试

### 文档更新
- 代码变更后同步更新文档
- 保持示例代码可运行

---

## 📝 编码规范

### Python 风格
- 遵循 PEP 8
- 函数添加 docstring
- 类型注解（Python 3.11+ 特性）

### 错误处理
```python
try:
    result = ebay_client.create_listing(sku)
except eBayAPIError as e:
    logger.error(f"Listing 创建失败：{e}")
    raise
```

### 日志记录
```python
import logging
logger = logging.getLogger(__name__)
logger.info(f"处理订单：{order_id}")
```

---

## 🧪 测试要求

### 单元测试
- 位置：`src/{module}/tests/`
- 运行：`pytest src/{module}/tests/`

### 集成测试
- 使用 sandbox 环境
- 不测试真实 API 调用（用 mock）

---

## 🔐 安全注意事项

### 禁止事项
- ❌ 提交 API 密钥、Token
- ❌ 硬编码凭证
- ❌ 提交真实用户数据

### 配置管理
- 敏感配置放入 `.gitignore`
- 使用 `.example` 模板

---

## 📊 评估检查清单

AI 助手在评估项目时请检查：

- [ ] 项目结构是否清晰
- [ ] 模块职责是否明确
- [ ] 错误处理是否完善
- [ ] 日志是否充分
- [ ] 测试覆盖率
- [ ] 文档完整性
- [ ] 代码重复度
- [ ] 依赖是否最新

---

## 🔄 协作流程

1. **理解需求**：阅读 Issue 描述
2. **分析代码**：定位相关模块
3. **制定计划**：在 Issue 中评论方案
4. **实施变更**：创建分支开发
5. **测试验证**：运行测试套件
6. **提交 PR**：关联 Issue

---

*最后更新：2026-03-30*
