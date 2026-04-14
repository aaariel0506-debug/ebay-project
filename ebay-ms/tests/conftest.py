"""tests/conftest.py — 全局测试配置"""
import pytest
from alembic import command
from alembic.config import Config


@pytest.fixture(scope="session", autouse=True)
def setup_database():
    """测试会话开始时执行迁移，确保 event_log 和 audit_log 表存在"""
    alembic_cfg = Config("alembic.ini")
    command.upgrade(alembic_cfg, "head")
    yield
