"""tests/test_models.py — Day 6 ORM 模型测试"""

from core.database.connection import get_session
from core.models import (
    EbayListing,
    Inventory,
    InventoryType,
    ListingStatus,
    Order,
    OrderItem,
    OrderStatus,
    Product,
    Transaction,
    TransactionType,
)


class TestEbayListing:
    """EbayListing ORM 测试"""

    def test_listing_status_enum(self):
        assert ListingStatus.ACTIVE == "active"
        assert ListingStatus.OUT_OF_STOCK == "out_of_stock"
        assert ListingStatus.ENDED == "ended"
        assert ListingStatus.DRAFT == "draft"

    def test_listing_fields(self):
        fields = [c.name for c in EbayListing.__table__.columns]
        assert "ebay_item_id" in fields
        assert "sku" in fields
        assert "listing_price" in fields
        assert "quantity_available" in fields
        assert "variants" in fields
        assert "status" in fields
        assert "last_synced" in fields


class TestInventory:
    """Inventory ORM 测试"""

    def test_inventory_type_enum(self):
        assert InventoryType.IN == "in"
        assert InventoryType.OUT == "out"
        assert InventoryType.ADJUST == "adjust"
        assert InventoryType.RETURN == "return"

    def test_inventory_fields(self):
        fields = [c.name for c in Inventory.__table__.columns]
        assert "sku" in fields
        assert "type" in fields
        assert "quantity" in fields
        assert "related_order" in fields


class TestOrder:
    """Order ORM 测试"""

    def test_order_status_enum(self):
        assert OrderStatus.PENDING == "pending"
        assert OrderStatus.SHIPPED == "shipped"
        assert OrderStatus.CANCELLED == "cancelled"
        assert OrderStatus.REFUNDED == "refunded"

    def test_order_fields(self):
        fields = [c.name for c in Order.__table__.columns]
        assert "ebay_order_id" in fields
        # sku 已移至 OrderItem 子表
        assert "sale_price" in fields
        assert "ebay_fee" in fields
        assert "buyer_country" in fields
        assert "status" in fields

    def test_orderitem_fields(self):
        """OrderItem 子表：每个订单的 SKU 明细"""
        fields = [c.name for c in OrderItem.__table__.columns]
        assert "id" in fields
        assert "order_id" in fields
        assert "sku" in fields
        assert "quantity" in fields
        assert "unit_price" in fields
        assert "sale_amount" in fields


class TestTransaction:
    """Transaction ORM 测试"""

    def test_transaction_type_enum(self):
        assert TransactionType.SALE == "sale"
        assert TransactionType.REFUND == "refund"
        assert TransactionType.FEE == "fee"
        assert TransactionType.SHIPPING == "shipping"
        assert TransactionType.ADJUSTMENT == "adjustment"

    def test_transaction_fields(self):
        fields = [c.name for c in Transaction.__table__.columns]
        assert "order_id" in fields
        assert "sku" in fields
        assert "type" in fields
        assert "amount" in fields
        assert "currency" in fields
        assert "amount_jpy" in fields


class _Helper:
    """测试辅助：创建测试商品"""
    @staticmethod
    def make_product(sku: str) -> Product:
        return Product(
            sku=sku,
            title="Test Product",
            cost_price=100.0,
            cost_currency="USD",
            status="active",
        )


class TestInventoryCrud:
    """Inventory CRUD 测试"""

    def setup_method(self):
        self._clear(Inventory)
        self._clear(Product)

    def _clear(self, model):
        with get_session() as s:
            s.query(model).delete()
            s.commit()

    def test_create_inventory_in(self):
        p = _Helper.make_product("TEST-INV-001")
        with get_session() as s:
            s.add(p)
            s.commit()

        inv = Inventory(
            sku="TEST-INV-001",
            type=InventoryType.IN,
            quantity=50,
            location="Warehouse-A",
            operator="admin",
        )
        with get_session() as s:
            s.add(inv)
            s.commit()
            assert inv.id is not None
            assert inv.type == InventoryType.IN
            assert inv.quantity == 50


class TestOrderCrud:
    """Order CRUD 测试"""

    def setup_method(self):
        self._clear(Order)
        self._clear(Product)

    def _clear(self, model):
        with get_session() as s:
            s.query(model).delete()
            s.commit()

    def test_create_order(self):
        p = _Helper.make_product("TEST-ORD-001")
        with get_session() as s:
            s.add(p)
            s.commit()

        # Order 无 sku 字段（sku 在 OrderItem）
        order = Order(
            ebay_order_id="ORD-TEST-001",
            sale_price=299.99,
            shipping_cost=5.99,
            ebay_fee=29.90,
            buyer_country="US",
            status=OrderStatus.PENDING,
        )
        with get_session() as s:
            s.add(order)
            s.flush()  # get order_id

            # OrderItem 对应 sku
            oi = OrderItem(
                order_id=order.ebay_order_id,
                sku=p.sku,
                quantity=1,
                unit_price=299.99,
                sale_amount=299.99,
            )
            s.add(oi)
            s.commit()

            saved = s.query(Order).filter(
                Order.ebay_order_id == "ORD-TEST-001"
            ).first()
            assert saved is not None
            assert saved.status == OrderStatus.PENDING

            saved_oi = s.query(OrderItem).filter(
                OrderItem.order_id == "ORD-TEST-001"
            ).first()
            assert saved_oi is not None
            assert saved_oi.sku == p.sku


class TestTransactionCrud:
    """Transaction CRUD 测试"""

    def setup_method(self):
        self._clear(Transaction)

    def _clear(self, model):
        with get_session() as s:
            s.query(model).delete()
            s.commit()

    def test_create_sale_transaction(self):
        txn = Transaction(
            type=TransactionType.SALE,
            amount=150.00,
            currency="USD",
            amount_jpy=150.00,
            note="Test sale",
        )
        with get_session() as s:
            s.add(txn)
            s.commit()
            assert txn.id is not None
            assert txn.type == TransactionType.SALE


class TestDay28_5:
    """Day 28.5: 新字段 total_due_seller_raw + sold_via_ad_campaign 测试"""

    def test_order_has_total_due_seller_raw_field(self, db_session):
        from decimal import Decimal

        from core.models import Order, OrderStatus

        order = Order(
            ebay_order_id="ORD-TDS-001",
            sale_price=Decimal("100.00"),
            shipping_cost=Decimal("5.00"),
            ebay_fee=Decimal("10.00"),
            buyer_country="US",
            status=OrderStatus.SHIPPED,
            total_due_seller_raw=Decimal("90.02"),
        )
        db_session.add(order)
        db_session.commit()

        saved = db_session.query(Order).filter(Order.ebay_order_id == "ORD-TDS-001").first()
        assert saved is not None
        assert saved.total_due_seller_raw == Decimal("90.02")

        order2 = Order(
            ebay_order_id="ORD-TDS-002",
            sale_price=Decimal("100.00"),
            shipping_cost=Decimal("5.00"),
            ebay_fee=Decimal("10.00"),
            buyer_country="US",
            status=OrderStatus.SHIPPED,
            total_due_seller_raw=None,
        )
        db_session.add(order2)
        db_session.commit()
        saved2 = db_session.query(Order).filter(Order.ebay_order_id == "ORD-TDS-002").first()
        assert saved2.total_due_seller_raw is None

    def test_order_has_sold_via_ad_campaign_field(self, db_session):
        from core.models import Order, OrderStatus

        order_true = Order(
            ebay_order_id="ORD-AD-001",
            sale_price=100.0,
            shipping_cost=0,
            ebay_fee=0,
            buyer_country="US",
            status=OrderStatus.SHIPPED,
            sold_via_ad_campaign=True,
        )
        db_session.add(order_true)
        db_session.commit()
        saved = db_session.query(Order).filter(Order.ebay_order_id == "ORD-AD-001").first()
        assert saved.sold_via_ad_campaign is True

        order_false = Order(
            ebay_order_id="ORD-AD-002",
            sale_price=100.0,
            shipping_cost=0,
            ebay_fee=0,
            buyer_country="US",
            status=OrderStatus.SHIPPED,
            sold_via_ad_campaign=False,
        )
        db_session.add(order_false)
        db_session.commit()
        saved2 = db_session.query(Order).filter(Order.ebay_order_id == "ORD-AD-002").first()
        assert saved2.sold_via_ad_campaign is False

        order_none = Order(
            ebay_order_id="ORD-AD-003",
            sale_price=100.0,
            shipping_cost=0,
            ebay_fee=0,
            buyer_country="US",
            status=OrderStatus.SHIPPED,
            sold_via_ad_campaign=None,
        )
        db_session.add(order_none)
        db_session.commit()
        saved3 = db_session.query(Order).filter(Order.ebay_order_id == "ORD-AD-003").first()
        assert saved3.sold_via_ad_campaign is None

    def test_alembic_roundtrip_adds_and_removes_new_fields(self, db_session):
        import sqlite3
        import subprocess
        import sys
        from pathlib import Path

        from core.config.settings import settings

        project_root = Path(__file__).parent.parent
        db_file = settings.db_path

        def run_alembic(*args):
            return subprocess.run(
                [sys.executable, "-m", "alembic", *args],
                cwd=str(project_root),
                capture_output=True,
                text=True,
                check=False,
            )

        def has_column(col_name):
            conn = sqlite3.connect(str(db_file))
            cols = conn.execute("PRAGMA table_info(orders)").fetchall()
            conn.close()
            return any(c[1] == col_name for c in cols)

        # upgrade 后应该有新列
        assert has_column("total_due_seller_raw"), "upgrade 后应该有 total_due_seller_raw 列"
        assert has_column("sold_via_ad_campaign"), "upgrade 后应该有 sold_via_ad_campaign 列"

        # downgrade -1
        r = run_alembic("downgrade", "-1")
        assert r.returncode == 0, f"downgrade failed: {r.stderr}"
        assert not has_column("total_due_seller_raw"), "downgrade 后 total_due_seller_raw 列应消失"
        assert not has_column("sold_via_ad_campaign"), "downgrade 后 sold_via_ad_campaign 列应消失"

        # 再 upgrade head
        r = run_alembic("upgrade", "head")
        assert r.returncode == 0, f"re-upgrade failed: {r.stderr}"
        assert has_column("total_due_seller_raw")
        assert has_column("sold_via_ad_campaign")


class TestDay31A:
    """Day 31-A: enum + Order 新字段 + migration 往返测试"""

    def test_transaction_type_enum_has_new_values(self):
        from core.models import TransactionType

        assert TransactionType.AD_FEE.value == "ad_fee"
        assert TransactionType.SALE_TAX.value == "sale_tax"
        assert TransactionType.SHIPPING_ACTUAL.value == "shipping_actual"
        # 老值不能动
        assert TransactionType.SALE.value == "sale"
        assert TransactionType.FEE.value == "fee"
        assert TransactionType.SHIPPING.value == "shipping"
        assert TransactionType.REFUND.value == "refund"
        assert TransactionType.ADJUSTMENT.value == "adjustment"

    def test_order_has_ad_fee_total_field(self, db_session):
        from decimal import Decimal

        from core.models import Order, OrderStatus

        order = Order(
            ebay_order_id="ORD-ADFEE-001",
            sale_price=Decimal("100.00"),
            shipping_cost=Decimal("0"),
            ebay_fee=Decimal("0"),
            buyer_country="US",
            status=OrderStatus.SHIPPED,
            ad_fee_total=Decimal("150.00"),
        )
        db_session.add(order)
        db_session.commit()

        saved = db_session.query(Order).filter(Order.ebay_order_id == "ORD-ADFEE-001").first()
        assert saved is not None
        assert saved.ad_fee_total == Decimal("150.00")

        order2 = Order(
            ebay_order_id="ORD-ADFEE-002",
            sale_price=Decimal("100.00"),
            shipping_cost=Decimal("0"),
            ebay_fee=Decimal("0"),
            buyer_country="US",
            status=OrderStatus.SHIPPED,
            ad_fee_total=None,
        )
        db_session.add(order2)
        db_session.commit()
        saved2 = db_session.query(Order).filter(Order.ebay_order_id == "ORD-ADFEE-002").first()
        assert saved2.ad_fee_total is None

    def test_order_has_buyer_paid_total_field(self, db_session):
        from decimal import Decimal

        from core.models import Order, OrderStatus

        order = Order(
            ebay_order_id="ORD-BP-001",
            sale_price=Decimal("100.00"),
            shipping_cost=Decimal("0"),
            ebay_fee=Decimal("0"),
            buyer_country="US",
            status=OrderStatus.SHIPPED,
            buyer_paid_total=Decimal("200.00"),
        )
        db_session.add(order)
        db_session.commit()

        saved = db_session.query(Order).filter(Order.ebay_order_id == "ORD-BP-001").first()
        assert saved is not None
        assert saved.buyer_paid_total == Decimal("200.00")

        order2 = Order(
            ebay_order_id="ORD-BP-002",
            sale_price=Decimal("100.00"),
            shipping_cost=Decimal("0"),
            ebay_fee=Decimal("0"),
            buyer_country="US",
            status=OrderStatus.SHIPPED,
            buyer_paid_total=None,
        )
        db_session.add(order2)
        db_session.commit()
        saved2 = db_session.query(Order).filter(Order.ebay_order_id == "ORD-BP-002").first()
        assert saved2.buyer_paid_total is None

    def test_alembic_roundtrip_adds_and_removes_ad_fee_and_buyer_paid_total(self, db_session):
        import sqlite3
        import subprocess
        import sys
        from pathlib import Path

        from core.config.settings import settings

        project_root = Path(__file__).parent.parent
        db_file = settings.db_path

        def run_alembic(*args):
            return subprocess.run(
                [sys.executable, "-m", "alembic", *args],
                cwd=str(project_root),
                capture_output=True,
                text=True,
                check=False,
            )

        def has_column(col_name):
            conn = sqlite3.connect(str(db_file))
            cols = conn.execute("PRAGMA table_info(orders)").fetchall()
            conn.close()
            return any(c[1] == col_name for c in cols)

        # 当前 migration head 应该有新列
        assert has_column("ad_fee_total"), "upgrade 后应该有 ad_fee_total 列"
        assert has_column("buyer_paid_total"), "upgrade 后应该有 buyer_paid_total 列"

        # downgrade -1
        r = run_alembic("downgrade", "-1")
        assert r.returncode == 0, f"downgrade failed: {r.stderr}"
        assert not has_column("ad_fee_total"), "downgrade 后 ad_fee_total 列应消失"
        assert not has_column("buyer_paid_total"), "downgrade 后 buyer_paid_total 列应消失"

        # 再 upgrade head
        r = run_alembic("upgrade", "head")
        assert r.returncode == 0, f"re-upgrade failed: {r.stderr}"
        assert has_column("ad_fee_total")
        assert has_column("buyer_paid_total")
