"""tests/test_validators.py — Day 6 Pydantic 校验测试"""
from datetime import datetime

import pytest
from core.utils.validators import (
    InventoryImport,
    OrderImport,
    ProductImport,
    TransactionImport,
    parse_datetime,
    validate_batch,
)
from pydantic import ValidationError as PydanticValidationError


class TestProductImport:
    def test_valid_product(self):
        p = ProductImport(
            sku="SKU-001",
            title="Test Product",
            cost_price=99.99,
            cost_currency="USD",
            status="active",
        )
        assert p.sku == "SKU-001"
        assert p.cost_price == 99.99

    def test_negative_price_fails(self):
        with pytest.raises(PydanticValidationError):
            ProductImport(
                sku="SKU-002",
                title="T",
                cost_price=-10.0,
                cost_currency="USD",
            )

    def test_invalid_currency_fails(self):
        with pytest.raises(PydanticValidationError):
            ProductImport(
                sku="SKU-003",
                title="T",
                cost_price=10.0,
                cost_currency="XYZ",
            )

    def test_invalid_status_fails(self):
        with pytest.raises(PydanticValidationError):
            ProductImport(
                sku="SKU-004",
                title="T",
                cost_price=10.0,
                cost_currency="USD",
                status="super_active",
            )


class TestOrderImport:
    def test_valid_order(self):
        o = OrderImport(
            ebay_order_id="ORD-123",
            sku="SKU-001",
            sale_price=199.99,
            shipping_cost=5.00,
            status="pending",
            order_date="2026-01-15 10:00:00",
        )
        assert o.ebay_order_id == "ORD-123"
        assert isinstance(o.order_date, datetime)

    def test_order_id_invalid_characters(self):
        with pytest.raises(PydanticValidationError):
            OrderImport(
                ebay_order_id="ORD-123!@#$",
                sku="SKU-001",
                sale_price=100.0,
            )

    def test_negative_price_fails(self):
        with pytest.raises(PydanticValidationError):
            OrderImport(
                ebay_order_id="ORD-999",
                sku="SKU-001",
                sale_price=-5.0,
            )

    def test_invalid_order_status(self):
        with pytest.raises(PydanticValidationError):
            OrderImport(
                ebay_order_id="ORD-000",
                sku="SKU-001",
                sale_price=100.0,
                status="delivered",
            )


class TestInventoryImport:
    def test_valid_inventory_in(self):
        inv = InventoryImport(
            sku="SKU-INV-001",
            type="in",
            quantity=100,
            location="WH-A",
            operator="admin",
        )
        assert inv.type == "in"
        assert inv.quantity == 100

    def test_invalid_type_fails(self):
        with pytest.raises(PydanticValidationError):
            InventoryImport(
                sku="SKU-INV-002",
                type="steal",
                quantity=10,
            )

    def test_zero_quantity_fails(self):
        with pytest.raises(PydanticValidationError):
            InventoryImport(
                sku="SKU-INV-003",
                type="out",
                quantity=0,
            )


class TestTransactionImport:
    def test_valid_sale(self):
        t = TransactionImport(
            type="sale",
            amount=250.00,
            currency="USD",
            amount_usd=250.00,
        )
        assert t.type == "sale"
        assert t.amount_usd == 250.00

    def test_invalid_type_fails(self):
        with pytest.raises(PydanticValidationError):
            TransactionImport(
                type="theft",
                amount=100.0,
            )

    def test_default_currency(self):
        t = TransactionImport(type="fee", amount=5.0)
        assert t.currency == "USD"


class TestValidateBatch:
    def test_batch_success_and_errors(self):
        records = [
            {"sku": "A", "title": "T", "cost_price": 10.0, "cost_currency": "USD"},
            {"sku": "B", "title": "T", "cost_price": -1.0, "cost_currency": "USD"},  # bad
            {"sku": "C", "title": "T", "cost_price": 20.0, "cost_currency": "USD"},
        ]
        result = validate_batch(ProductImport, records)
        assert len(result.success) == 2
        assert len(result.errors) == 1
        assert result.errors[0]["index"] == 1

    def test_batch_all_errors(self):
        records = [
            {"sku": "", "title": "T", "cost_price": 10.0, "cost_currency": "USD"},
            {"sku": "X", "title": "", "cost_price": -1.0, "cost_currency": "INVALID"},
        ]
        result = validate_batch(ProductImport, records)
        assert len(result.success) == 0
        assert len(result.errors) == 2


class TestParseDatetime:
    def test_parse_various_formats(self):
        assert parse_datetime("2026-01-15 10:00:00") is not None
        assert parse_datetime("2026-01-15") is not None
        assert parse_datetime("01/15/2026 10:00:00") is not None
        assert parse_datetime(None) is None
        assert isinstance(parse_datetime("2026-01-15"), datetime)
