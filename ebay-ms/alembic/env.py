"""
alembic/env.py
Alembic 迁移配置，连接到 ebay-ms 数据库
"""
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool
from sqlalchemy.engine import Connection

import sys
from pathlib import Path

# 将项目根加入 path
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.models.base import Base
from core.models.product import Product  # noqa: F401
from core.database.connection import get_engine
from core.config.settings import settings

# Alembic Config object
config = context.config

# 解析 logging
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# 指向我们的模型 metadata
target_metadata = Base.metadata

# 从 settings 读取数据库 URL（覆盖 alembic.ini 中的配置）
db_url = f"sqlite:///{settings.db_path}"
config.set_main_option("sqlalchemy.url", db_url)


def run_migrations_offline() -> None:
    """离线模式：不需要 DBAPI 连接"""
    context.configure(
        url=db_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """在线模式：使用 engine"""
    connectable: Connection = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
