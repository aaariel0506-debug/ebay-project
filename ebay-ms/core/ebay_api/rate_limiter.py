"""
core/ebay_api/rate_limiter.py — eBay API 限流控制

特性：
- 按 endpoint 追踪每日调用次数
- 80% 限额 → WARNING 日志
- 95% 限额 → 拒绝请求，抛 EbayRateLimitError
- 计数持久化到 SQLite（重启不丢）
- 每日零点自动重置（UTC）
"""
import threading
from datetime import datetime, timezone
from pathlib import Path

from core.config.settings import settings
from core.ebay_api.exceptions import EbayRateLimitError
from loguru import logger

# 默认限流值（次/天），可被配置文件覆盖
DEFAULT_DAILY_LIMIT = 5000
WARNING_THRESHOLD = 0.80  # 80%
REJECT_THRESHOLD = 0.95  # 95%


class RateLimitStore:
    """
    SQLite 持久化限流计数器。

    表结构：
        rate_counts(endpoint TEXT PK, date TEXT, count INTEGER)
    """

    def __init__(self, db_path: Path):
        self.db_path = db_path
        # RLock(可重入锁):必须用,因为 increment() 在持有锁时还会调 get_count()
        # 自身,二者用同一把锁。普通 Lock 会自我死锁(EbayClient.get → _request →
        # rate_limiter.record → check + increment → 持锁中调 get_count → 死)。
        self._lock = threading.RLock()
        self._ensure_table()

    def _ensure_table(self):
        import sqlite3
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS rate_counts (
                    endpoint TEXT NOT NULL,
                    date TEXT NOT NULL,
                    count INTEGER NOT NULL DEFAULT 0,
                    PRIMARY KEY (endpoint, date)
                )
                """
            )

    def _today(self) -> str:
        return datetime.now(timezone.utc).strftime("%Y-%m-%d")

    def get_count(self, endpoint: str) -> int:
        with self._lock:
            import sqlite3
            try:
                with sqlite3.connect(self.db_path) as conn:
                    cur = conn.execute(
                        "SELECT count FROM rate_counts WHERE endpoint=? AND date=?",
                        (endpoint, self._today()),
                    )
                    row = cur.fetchone()
                    return row[0] if row else 0
            except sqlite3.Error:
                return 0

    def increment(self, endpoint: str) -> int:
        with self._lock:
            import sqlite3
            today = self._today()
            with sqlite3.connect(self.db_path) as conn:
                conn.execute(
                    """
                    INSERT INTO rate_counts (endpoint, date, count)
                    VALUES (?, ?, 1)
                    ON CONFLICT(endpoint, date) DO UPDATE SET count = count + 1
                    """,
                    (endpoint, today),
                )
                conn.commit()
            # 返回增加后的计数
            return self.get_count(endpoint)


class RateLimiter:
    """
    eBay API 限流器。

    加载限流配置（硬编码字典），追踪每日调用，
    达到阈值时警告或拒绝。
    """

    def __init__(self, store: RateLimitStore | None = None):
        from core.ebay_api.rate_limit_config import RATE_LIMITS
        self._store = store or RateLimitStore(settings.db_path.parent / "rate_limits.db")
        self._limits: dict[str, int] = RATE_LIMITS  # endpoint_prefix -> daily_limit
        self._warned: set[str] = set()  # 今天已警告过的 endpoint

    def _get_limit(self, endpoint: str) -> int:
        """按前缀匹配返回限额，未知 endpoint 用默认值"""
        for prefix, limit in self._limits.items():
            if endpoint.startswith(prefix):
                return limit
        return DEFAULT_DAILY_LIMIT

    def _today_key(self) -> str:
        return datetime.now(timezone.utc).strftime("%Y-%m-%d")

    def check(self, endpoint: str) -> None:
        """
        检查限流，在限额内直接通过。

        达到 80% 限额记录 WARNING，达到 95% 抛异常。
        """
        count = self._store.get_count(endpoint)
        limit = self._get_limit(endpoint)
        ratio = count / limit

        if ratio >= REJECT_THRESHOLD:
            raise EbayRateLimitError(
                f"限流触发 [{endpoint}]：已用 {count}/{limit} ({ratio:.0%})",
                retry_after=None,
            )

        if ratio >= WARNING_THRESHOLD and endpoint not in self._warned:
            logger.warning(
                "eBay API 限流警告 [{endpoint}]：已用 {count}/{limit} ({ratio:.0%})",
                endpoint=endpoint, count=count, limit=limit, ratio=ratio
            )
            self._warned.add(endpoint)

    def record(self, endpoint: str) -> int:
        """记录一次调用，返回当前计数"""
        self.check(endpoint)
        return self._store.increment(endpoint)

    @property
    def is_loaded(self) -> bool:
        return True


# 全局单例（延迟初始化）
_rate_limiter: RateLimiter | None = None


def get_rate_limiter() -> RateLimiter:
    global _rate_limiter
    if _rate_limiter is None:
        _rate_limiter = RateLimiter()
    return _rate_limiter
