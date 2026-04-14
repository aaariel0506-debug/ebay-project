"""modules.listing.schemas — Pydantic schemas for Listing operations"""
from datetime import datetime
from typing import Annotated
from pydantic import BaseModel, Field, field_validator


# ── Request Schemas ───────────────────────────────────────

class InventoryItemRequest(BaseModel):
    """Step 1: createOrReplaceInventoryItem 请求体"""
    model_config = {"str_strip_whitespace": True}

    sku: Annotated[str, Field(min_length=1, max_length=64, description="商品 SKU")]
    availability: dict = Field(
        description="库存可用性",
        default_factory=lambda: {
            "shipToLocationAvailability": {
                "quantity": 0,
            }
        },
    )
    condition: Annotated[str, Field(min_length=1, max_length=30, description="商品状况")]
    condition_description: str | None = None
    product: dict | None = None  # eBay product identifier
    package_weight_and_size: dict | None = None


class OfferRequest(BaseModel):
    """Step 2: createOffer 请求体"""
    model_config = {"str_strip_whitespace": True}

    sku: Annotated[str, Field(min_length=1, max_length=64)]
    marketplace_id: Annotated[str, Field(min_length=1, description="eBay 市场 ID，如 EBAY_US")]
    listing_description: str | None = None
    listing_policies: dict | None = None  # fulfillment_policy_id, return_policy_id, payment_policy_id
    pricing_summary: dict | None = None   # { "price": { "currency": "USD", "value": "19.99" } }
    quantity: int = 0


class ListingCreateRequest(BaseModel):
    """
    完整创建 Listing 的请求（合并 3 个步骤）
    使用时需提供所有必需字段，service 自动分步调用 API。
    """
    model_config = {"str_strip_whitespace": True}

    sku: Annotated[str, Field(min_length=1, max_length=64, description="关联商品 SKU")]
    title: Annotated[str, Field(min_length=1, max_length=80, description="Listing 标题")]
    description: str | None = None
    category_id: str | None = None
    condition: Annotated[str, Field(min_length=1, description="NEW / VERY_GOOD / GOOD / ACCEPTABLE 等")]
    condition_description: str | None = None
    listing_price: Annotated[float, Field(gt=0, description="上架价格")]
    quantity: Annotated[int, Field(ge=0, description="可售数量")]
    image_urls: list[str] = Field(default_factory=list, max_length=12)
    fulfillment_policy_id: str | None = None
    return_policy_id: str | None = None
    payment_policy_id: str | None = None
    currency: Annotated[str, Field(min_length=3, max_length=3, default="USD")]
    marketplace_id: str = "EBAY_US"


# ── Response Schemas ───────────────────────────────────────

class InventoryItemResponse(BaseModel):
    """Step 1 响应"""
    sku: str
    status: str


class OfferResponse(BaseModel):
    """Step 2 响应"""
    offer_id: str
    sku: str
    status: str


class PublishResponse(BaseModel):
    """Step 3 响应"""
    offer_id: str
    listing_id: str
    status: str
    listing_id_href: str | None = None


class ListingCreateResponse(BaseModel):
    """完整创建 Listing 响应"""
    success: bool
    ebay_item_id: str | None = None
    offer_id: str | None = None
    sku: str
    status: str | None = None
    errors: list[str] = Field(default_factory=list)


class ListingRecord(BaseModel):
    """数据库 Listing 记录"""
    ebay_item_id: str
    sku: str
    title: str | None = None
    listing_price: float
    quantity_available: int
    status: str
    last_synced: datetime | None = None
