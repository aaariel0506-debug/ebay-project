"""modules.listing.schemas — Pydantic schemas for Listing operations"""
from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, Field

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


# ── Variant Listing Schemas ─────────────────────────────────

class VariantSpecific(BaseModel):
    """单个变体维度，如 Size=M，或 Color=Red"""
    name: Annotated[str, Field(min_length=1, max_length=50, description="维度名称，如 Size/Color")]
    value: Annotated[str, Field(min_length=1, max_length=50, description="维度值，如 M/Red")]


class VariantItem(BaseModel):
    """
    单个变体商品。
    独立 SKU、独立价格、独立库存。
    """
    sku: Annotated[str, Field(min_length=1, max_length=64)]
    variant_specifics: list[VariantSpecific] = Field(
        description="变体维度列表，如 [VariantSpecific(name='Size',value='M'), VariantSpecific(name='Color',value='Red')]"
    )
    price: Annotated[float, Field(gt=0, description="此变体的上架价格")]
    quantity: int = 0  # eBay requires ge=0 but defaults to 0
    condition: str = "NEW"
    image_urls: list[str] = Field(default_factory=list, max_length=12)


class InventoryItemGroupRequest(BaseModel):
    """
    eBay Inventory Item Group 请求体。
    将多个 VariantItem 组合为一个多变体 Listing。
    """
    model_config = {"str_strip_whitespace": True}

    group_id: str | None = Field(
        default=None,
        description="变体组 ID（留空则由 eBay 自动生成）",
    )
    group_description: str | None = Field(
        default=None,
        description="变体组商品描述（会在每个变体页面显示）",
    )
    group_title: Annotated[str, Field(min_length=1, max_length=80, description="变体组标题")]
    brand: str | None = None
    category_id: str | None = None
    condition: str = "NEW"
    image_urls: list[str] = Field(default_factory=list, max_length=12)
    variants: list[VariantItem] = Field(min_length=2, description="至少 2 个变体")
    marketplace_id: str = "EBAY_US"
    currency: str = "USD"
    fulfillment_policy_id: str | None = None
    return_policy_id: str | None = None
    payment_policy_id: str | None = None


class VariantListingCreateResponse(BaseModel):
    """变体 Listing 创建响应"""
    success: bool
    group_id: str | None = None
    variants: list[dict] = Field(default_factory=list, description="每个变体的 {sku, offer_id, listing_id, status}")
    errors: list[str] = Field(default_factory=list)


# ── Image Upload Schemas ─────────────────────────────────────

class ImageUploadRequest(BaseModel):
    """
    图片上传请求。
    支持两种来源：本地文件路径 或 外部 URL。
    eBay Inventory API 接受外部 URL 作为 pictureUrls，不需要单独上传步骤。
    """
    source_type: Annotated[str, Field(pattern="^(file|url)$", description="'file' 或 'url'")]
    paths: list[str] = Field(min_length=1, max_length=12, description="文件路径列表或 URL 列表")
    sku: str | None = Field(default=None, description="关联的 SKU（可选）")


class ImageValidationResult(BaseModel):
    """单张图片校验结果"""
    path: str  # 文件路径或 URL
    valid: bool
    error: str | None = None
    size_bytes: int | None = None
    format: str | None = None  # jpg / png / gif / webp


class ImageUploadResponse(BaseModel):
    """图片上传/校验响应"""
    total: int
    valid_count: int
    invalid_count: int
    accepted_urls: list[str] = Field(default_factory=list, description="校验通过、可提交给 eBay 的 URL 列表")
    results: list[ImageValidationResult] = Field(default_factory=list)
