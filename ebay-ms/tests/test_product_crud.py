"""
tests/test_product_crud.py
Product 模型 CRUD 测试
"""
from decimal import Decimal

import pytest
from core.database.connection import get_engine, get_session
from core.models.base import Base
from core.models.product import Product, ProductStatus
from sqlalchemy import select


@pytest.fixture(scope="function")
def fresh_db():
    """每个测试使用干净的数据库"""
    engine = get_engine()
    # 建表
    Base.metadata.create_all(bind=engine)
    yield
    # 清理
    with engine.connect() as conn:
        for table in Base.metadata.sorted_tables:
            conn.execute(table.delete())
        conn.commit()


class TestProductCRUD:
    """Product CRUD 测试套件"""

    def test_create(self, fresh_db):
        """测试创建 Product"""
        with get_session() as s:
            p = Product(
                sku="02-2603-0001",
                title="神話オラクルカード",
                category=" Tarot Cards",
                cost_price=Decimal("3800.00"),
                cost_currency="JPY",
                supplier="Amazon JP",
                status=ProductStatus.ACTIVE,
            )
            s.add(p)
            s.commit()
            s.refresh(p)
            assert p.sku == "02-2603-0001"
            assert p.title == "神話オラクルカード"
            assert p.cost_price == Decimal("3800.00")
            assert p.status == ProductStatus.ACTIVE
            assert p.created_at is not None
            print(f"✓ CREATE: {p}")

    def test_read(self, fresh_db):
        """测试读取 Product"""
        with get_session() as s:
            p = Product(
                sku="02-2603-0002",
                title="Test Product",
                cost_price=Decimal("1500.00"),
                cost_currency="JPY",
                status=ProductStatus.ACTIVE,
            )
            s.add(p)
            s.commit()

        # 新 session 中读取
        with get_session() as s:
            result = s.execute(select(Product).where(Product.sku == "02-2603-0002"))
            found = result.scalar_one()
            assert found.title == "Test Product"
            assert found.cost_price == Decimal("1500.00")
            print(f"✓ READ: {found}")

    def test_update(self, fresh_db):
        """测试更新 Product"""
        with get_session() as s:
            p = Product(
                sku="02-2603-0003",
                title="Original Title",
                cost_price=Decimal("1000.00"),
                cost_currency="JPY",
                status=ProductStatus.ACTIVE,
            )
            s.add(p)
            s.commit()

        with get_session() as s:
            result = s.execute(select(Product).where(Product.sku == "02-2603-0003"))
            p = result.scalar_one()
            p.title = "Updated Title"
            p.cost_price = Decimal("1200.00")
            p.status = ProductStatus.OUT_OF_STOCK
            s.commit()
            s.refresh(p)
            assert p.title == "Updated Title"
            assert p.cost_price == Decimal("1200.00")
            assert p.status == ProductStatus.OUT_OF_STOCK
            print(f"✓ UPDATE: {p}")

    def test_delete(self, fresh_db):
        """测试删除 Product"""
        with get_session() as s:
            p = Product(
                sku="02-2603-0004",
                title="To Be Deleted",
                cost_price=Decimal("500.00"),
                cost_currency="JPY",
                status=ProductStatus.ACTIVE,
            )
            s.add(p)
            s.commit()

        with get_session() as s:
            result = s.execute(select(Product).where(Product.sku == "02-2603-0004"))
            p = result.scalar_one()
            s.delete(p)
            s.commit()

        with get_session() as s:
            result = s.execute(select(Product).where(Product.sku == "02-2603-0004"))
            found = result.scalar_one_or_none()
            assert found is None
            print("✓ DELETE: 记录已删除")

    def test_status_enum(self, fresh_db):
        """测试 status 枚举值"""
        with get_session() as s:
            for status in ProductStatus:
                p = Product(
                    sku=f"SKU-{status.value}",
                    title=f"Product {status.value}",
                    cost_price=Decimal("100.00"),
                    cost_currency="JPY",
                    status=status,
                )
                s.add(p)
            s.commit()

        with get_session() as s:
            result = s.execute(select(Product))
            products = result.scalars().all()
            assert len(products) == 3
            statuses = {p.status for p in products}
            assert statuses == {ProductStatus.ACTIVE, ProductStatus.DISCONTINUED, ProductStatus.OUT_OF_STOCK}
            print(f"✓ ENUM: statuses = {statuses}")

    def test_required_fields(self, fresh_db):
        """测试必填字段校验"""
        with get_session() as s:
            # sku 缺失应报错
            p = Product(title="No SKU", cost_price=Decimal("100.00"), cost_currency="JPY")
            s.add(p)
            with pytest.raises(Exception):
                s.commit()
            s.rollback()
            print("✓ REQUIRED: sku is primary key (enforced by DB)")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
