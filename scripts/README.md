# Scripts 工具脚本

## 活跃脚本

| 脚本 | 用途 | 使用方法 |
|------|------|----------|
| `ebay_token_manager.py` | eBay OAuth Token 管理（获取、刷新、缓存） | `python ebay_token_manager.py` |
| `ebay_oauth_get_refresh_token.py` | 获取 eBay Refresh Token（首次授权用） | `python ebay_oauth_get_refresh_token.py` |
| `ebay_create_location.py` | 创建 eBay 商家位置（Listing 前置步骤） | `python ebay_create_location.py` |
| `ebay_full_listing_workflow.py` | 完整 Listing 上架流程（创建+发布） | `python ebay_full_listing_workflow.py` |

## archive/ 归档脚本

迭代开发中的旧版本，保留供参考，不建议使用。

| 脚本 | 说明 |
|------|------|
| `ebay_publish_*.py` (5个) | 发布功能的早期版本，已整合到 listing-system |
| `ebay_listing_*.py` (4个) | Listing 创建的早期版本 |
| `ebay_*_simple.py` / `ebay_trading_*.py` | 沙盒测试和 Trading API 实验脚本 |
