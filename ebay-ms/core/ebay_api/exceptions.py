"""
core/ebay_api/exceptions.py
eBay API 自定义异常体系
"""


class EbayApiError(Exception):
    """eBay API 基础异常"""

    def __init__(self, message: str, status_code: int | None = None, response_body: str = ""):
        self.status_code = status_code
        self.response_body = response_body
        super().__init__(message)


class EbayAuthError(EbayApiError):
    """认证/授权失败（401/403、token 过期、refresh 失败）"""
    pass


class EbayRateLimitError(EbayApiError):
    """触发速率限制（429）"""

    def __init__(self, message: str, retry_after: int | None = None, **kwargs):
        self.retry_after = retry_after
        super().__init__(message, **kwargs)


class EbayNotFoundError(EbayApiError):
    """资源不存在（404）"""
    pass


class EbayServerError(EbayApiError):
    """eBay 服务端错误（5xx）"""
    pass


class EbayTokenMissingError(EbayAuthError):
    """本地缺少必要 token（refresh_token 未存储等）"""
    pass
