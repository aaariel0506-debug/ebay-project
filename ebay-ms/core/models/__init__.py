"""core.models — 所有 ORM 模型"""
from core.models.base import Base, TimestampMixin
from core.models.batch import BatchProgress
from core.models.inbound import InboundReceipt, InboundReceiptItem, InboundStatus
from core.models.inventory import Inventory, InventoryType
from core.models.listing import EbayListing, ListingStatus
from core.models.order import Order, OrderStatus
from core.models.price_history import SupplierPriceHistory
from core.models.product import Product, ProductStatus
from core.models.template import ListingTemplate
from core.models.transaction import Transaction, TransactionType
from sqlalchemy.orm import relationship

__all__ = [
    "Base",
    "TimestampMixin",
    "Product",
    "ProductStatus",
    "EbayListing",
    "ListingStatus",
    "Inventory",
    "InventoryType",
    "Order",
    "OrderStatus",
    "Transaction",
    "TransactionType",
    "ListingTemplate",
    "BatchProgress",
    "SupplierPriceHistory",
    "InboundReceipt",
    "InboundReceiptItem",
    "InboundStatus",
]

# Product → SupplierPriceHistory 反向关联（在模块加载时设置）
Product._price_history = relationship(  # type: ignore[attr-defined]
    "SupplierPriceHistory",
    back_populates="product",
    lazy="select",
    order_by="desc(SupplierPriceHistory.recorded_at)",
)
