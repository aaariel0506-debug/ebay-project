"""EbayListing ORM — eBay 挂单数据模型"""
import enum
from datetime import datetime

from core.models.base import Base, TimestampMixin
from sqlalchemy import JSON, DateTime, Enum, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column


class ListingStatus(enum.StrEnum):
    ACTIVE = "active"
    OUT_OF_STOCK = "out_of_stock"
    ENDED = "ended"
    DRAFT = "draft"


class EbayListing(Base, TimestampMixin):
    """
    eBay 挂单信息

    关联：sku -> Product.sku（外键）
    """
    __tablename__ = "ebay_listings"

    ebay_item_id: Mapped[str] = mapped_column(
        String(64), primary_key=True, doc="eBay Item ID（PK）"
    )
    sku: Mapped[str] = mapped_column(
        String(64), ForeignKey("products.sku"), nullable=False, index=True, doc="关联商品 SKU"
    )
    title: Mapped[str | None] = mapped_column(String(256), nullable=True)
    listing_price: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False, doc="上架价格")
    quantity_available: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    variants: Mapped[dict | None] = mapped_column(JSON, nullable=True, doc="多属性变体 JSON")
    status: Mapped[ListingStatus] = mapped_column(
        Enum(ListingStatus), nullable=False, default=ListingStatus.DRAFT, index=True
    )
    last_synced: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, doc="最后同步时间")
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    category: Mapped[str | None] = mapped_column(String(128), nullable=True)
    condition: Mapped[str | None] = mapped_column(String(32), nullable=True)
    image_urls: Mapped[list | None] = mapped_column(JSON, nullable=True)
