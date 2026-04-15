"""tests/conftest.py — 全局测试配置"""
import pytest
from alembic import command
from alembic.config import Config
from core.database.connection import get_engine


@pytest.fixture(scope="session", autouse=True)
def setup_database():
    """测试会话开始时执行迁移，确保 event_log 和 audit_log 表存在"""
    alembic_cfg = Config("alembic.ini")
    command.upgrade(alembic_cfg, "head")
    yield


@pytest.fixture(scope="function")
def db_session():
    """每个测试函数一个独立事务，测试结束时 rollback。"""
    import core.database.connection as conn_module

    # 创建独立连接 + 事务
    connection = get_engine().connect()
    transaction = connection.begin()

    # 创建绑定到该连接的 SessionFactory
    from sqlalchemy.orm import sessionmaker
    test_factory = sessionmaker(bind=connection)
    original_factory = conn_module._SessionLocal
    conn_module._SessionLocal = test_factory

    # 用 test_factory 打开 session
    session = test_factory()

    yield session

    session.close()
    transaction.rollback()
    connection.close()
    conn_module._SessionLocal = original_factory


@pytest.fixture(scope="function")
def sample_product(db_session):
    """创建测试用 Product。"""
    from decimal import Decimal

    from core.models import Product, ProductStatus
    prod = Product(
        sku="TEST-SKU-001",
        title="Test Product",
        cost_price=Decimal("100.00"),
        cost_currency="JPY",
        status=ProductStatus.ACTIVE,
        supplier="Test Supplier",
    )
    db_session.add(prod)
    db_session.commit()
    return prod
