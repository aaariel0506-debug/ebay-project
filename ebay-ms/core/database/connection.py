"""
core/database/connection.py
SQLite + WAL 模式数据库连接管理
"""
from contextlib import contextmanager

from core.config.settings import settings
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool


def _setup_wal_mode(dbapi_conn, connection_record) -> None:
    """启用 WAL 模式，提升并发性能"""
    cursor = dbapi_conn.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA synchronous=NORMAL")
    cursor.execute("PRAGMA busy_timeout=5000")
    cursor.close()


_engine = None
_SessionLocal = None


def get_engine():
    """全局 engine 单例（延迟创建）"""
    global _engine
    if _engine is None:
        settings.DB_DIR.mkdir(parents=True, exist_ok=True)
        db_url = f"sqlite:///{settings.db_path}"
        _engine = create_engine(
            db_url,
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
            echo=False,
        )
        event.listen(_engine, "connect", _setup_wal_mode)
    return _engine


def get_session_factory():
    """全局 Session 工厂单例"""
    global _SessionLocal
    if _SessionLocal is None:
        _SessionLocal = sessionmaker(
            bind=get_engine(),
            autocommit=False,
            autoflush=False,
        )
    return _SessionLocal


@contextmanager
def get_session() -> Session:
    """
    数据库 Session 上下文管理器。
    用法：
        with get_session() as session:
            session.query(...)
    自动 commit，异常自动 rollback。
    """
    SessionFactory = get_session_factory()
    session: Session = SessionFactory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
