"""
eBay MS - 统一配置管理
所有配置从 .env 读取，支持多环境切换（dev/prod）
"""
from pathlib import Path
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """统一配置类，从 .env 自动加载"""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── 环境 ──────────────────────────────────────────────
    ENV: Literal["dev", "prod"] = "dev"

    # ── eBay API ──────────────────────────────────────────
    EBAY_APP_ID: str = ""
    EBAY_CERT_ID: str = ""
    EBAY_DEV_ID: str = ""
    EBAY_ENV: Literal["sandbox", "production"] = "sandbox"

    # ── 数据库 ─────────────────────────────────────────────
    DB_DIR: Path = Path.home() / ".ebay-project" / "data"
    DB_NAME: str = "ebay.db"

    # ── 日志 ───────────────────────────────────────────────
    LOG_LEVEL: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    LOG_DIR: Path = Path.home() / ".ebay-project" / "logs"

    # ── 备份 ───────────────────────────────────────────────
    BACKUP_DIR: Path = Path.home() / ".ebay-project" / "backups"
    BACKUP_RETENTION_DAYS: int = 7

    # ── 安全 ───────────────────────────────────────────────
    # Token 加密密钥（请在 .env 中设置，不提交到 git）
    TOKEN_ENCRYPTION_KEY: str = ""

    @property
    def db_path(self) -> Path:
        self.DB_DIR.mkdir(parents=True, exist_ok=True)
        return self.DB_DIR / self.DB_NAME

    @property
    def ebay_oauth_url(self) -> str:
        if self.EBAY_ENV == "sandbox":
            return "https://api.sandbox.ebay.com/identity/v1/oauth2/token"
        return "https://api.ebay.com/identity/v1/oauth2/token"

    @property
    def ebay_api_url(self) -> str:
        if self.EBAY_ENV == "sandbox":
            return "https://api.sandbox.ebay.com"
        return "https://api.ebay.com"

    @property
    def ebay_finances_url(self) -> str:
        """Finances API 的 base URL（apiz.ebay.com，和 Fulfillment API 不同域）"""
        if self.EBAY_ENV == "sandbox":
            return "https://apiz.sandbox.ebay.com"
        return "https://apiz.ebay.com"


# 全局单例
settings = Settings()
