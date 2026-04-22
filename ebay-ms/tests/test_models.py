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
