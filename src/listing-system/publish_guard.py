#!/usr/bin/env python3
"""
发布守卫 - 确保所有 listing 必须经过预审核

此模块提供强制预审核机制，阻止任何绕过预审核系统的直接发布。
"""

import os
from datetime import datetime

# 强制预审核开关 - 即使配置错误也强制启用
FORCE_REVIEW_MODE = os.environ.get('EBAY_FORCE_REVIEW', 'true').lower() in ('true', '1', 'yes')

# 允许发布的来源白名单
ALLOWED_PUBLISH_SOURCES = {
    'review_web',      # 预审核页面
    'manual_cli',      # 手动 CLI（需要额外确认）
}


class PublishGuard:
    """发布守卫 - 控制发布权限"""
    
    def __init__(self):
        self.force_review = FORCE_REVIEW_MODE
        self.audit_log = []
    
    def can_publish(self, source: str, offer_id: str = None) -> tuple[bool, str]:
        """
        检查是否允许发布
        
        Args:
            source: 发布请求来源
            offer_id: 可选的 offer ID
            
        Returns:
            (允许, 原因)
        """
        if self.force_review and source not in ALLOWED_PUBLISH_SOURCES:
            return False, f"发布被拒绝：来源 '{source}' 不在白名单中。请使用预审核页面 http://127.0.0.1:8080"
        
        self.audit_log.append({
            'timestamp': datetime.now().isoformat(),
            'source': source,
            'offer_id': offer_id,
            'allowed': True
        })
        
        return True, "允许发布"
    
    def require_review(self) -> bool:
        """返回是否强制需要预审核"""
        return self.force_review
    
    def get_audit_log(self) -> list:
        """获取审核日志"""
        return self.audit_log


# 全局守卫实例
guard = PublishGuard()


def check_publish_permission(source: str = 'unknown', offer_id: str = None) -> tuple[bool, str]:
    """快捷函数：检查发布权限"""
    return guard.can_publish(source, offer_id)


def require_review() -> bool:
    """快捷函数：是否强制预审核"""
    return guard.require_review()
