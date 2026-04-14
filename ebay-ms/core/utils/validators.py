"""core.utils.validators — Pydantic 校验 Schema，用于外部数据导入"""
import re
from datetime import datetime
from enum import Enum
from typing import Annotated

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    ValidationError,
    field_validator,
)

# ── 通用工具 ──────────────────────────────────────────────

class Currency(str, Enum):
    USD = "USD"
    JPY = "JPY"
    GBP = "GBP"
    EUR = "EUR"
    CAD = "CAD"
    AUD = "AUD"


def parse_datetime(v: str | datetime | None) -> datetime | None:
    if v is None:
        return None
    if isinstance(v, datetime):
        return v
    # 尝试多种格式
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d", "%m/%d/%Y %H:%M:%S", "%m/%d/%Y"):
        try:
            return datetime.strptime(v, fmt)
        except ValueError:
            continue
    return None


# ── ProductImport ──────────────────────────────────────────

class ProductImport(BaseModel):
    """商品数据导入校验"""
    model_config = ConfigDict(str_strip_whitespace=True)

    sku: Annotated[str, Field(min_length=1, max_length=64, description="商品 SKU")]
    title: Annotated[str, Field(min_length=1, max_length=256)]
    category: str | None = None
    source_url: str | None = None
    cost_price: Annotated[float, Field(gt=0, description="成本价必须为正数")]
    cost_currency: Annotated[str, Field(min_length=3, max_length=3)]
    supplier: str | None = None
    status: str = "active"

    @field_validator("cost_currency")
    @classmethod
    def currency_must_be_valid(cls, v: str) -> str:
        v = v.upper()
        try:
            Currency(v)
        except ValueError:
            raise ValueError(f"currency must be one of: {[c.value for c in Currency]}")
        return v

    @field_validator("status")
    @classmethod
    def status_must_be_valid(cls, v: str) -> str:
        allowed = {"active", "discontinued", "draft"}
        if v.lower() not in allowed:
            raise ValueError(f"status must be one of: {allowed}")
        return v.lower()


# ── OrderImport ────────────────────────────────────────────

class OrderImport(BaseModel):
    """订单数据导入校验"""
    model_config = ConfigDict(str_strip_whitespace=True)

    ebay_order_id: Annotated[str, Field(min_length=1, max_length=64, description="eBay Order ID")]
    sku: Annotated[str, Field(min_length=1, max_length=64)]
    sale_price: Annotated[float, Field(ge=0, description="销售价非负")]
    shipping_cost: float = 0.0
    ebay_fee: float = 0.0
    buyer_country: str | None = None
    status: str = "pending"
    order_date: str | datetime | None = None
    ship_date: str | datetime | None = None

    @field_validator("ebay_order_id")
    @classmethod
    def ebay_order_id_format(cls, v: str) -> str:
        # eBay Order ID 通常是数字字符串
        if not re.match(r"^[A-Za-z0-9_\-]+$", v):
            raise ValueError("ebay_order_id contains invalid characters")
        return v

    @field_validator("order_date", "ship_date", mode="before")
    @classmethod
    def parse_date(cls, v: str | datetime | None) -> datetime | None:
        return parse_datetime(v)

    @field_validator("status")
    @classmethod
    def status_must_be_valid(cls, v: str) -> str:
        allowed = {"pending", "shipped", "cancelled", "refunded"}
        if v.lower() not in allowed:
            raise ValueError(f"status must be one of: {allowed}")
        return v.lower()


# ── EbayListingImport ──────────────────────────────────────

class EbayListingImport(BaseModel):
    """eBay Listing 导入校验"""
    model_config = ConfigDict(str_strip_whitespace=True)

    ebay_item_id: Annotated[str, Field(min_length=1, max_length=64)]
    sku: Annotated[str, Field(min_length=1, max_length=64)]
    title: str | None = None
    listing_price: Annotated[float, Field(ge=0)]
    quantity_available: int = 0
    variants: dict | None = None
    status: str = "draft"
    category: str | None = None
    condition: str | None = None

    @field_validator("listing_price")
    @classmethod
    def price_must_be_positive(cls, v: float) -> float:
        if v < 0:
            raise ValueError("listing_price must be non-negative")
        return v

    @field_validator("status")
    @classmethod
    def status_must_be_valid(cls, v: str) -> str:
        allowed = {"active", "out_of_stock", "ended", "draft"}
        if v.lower() not in allowed:
            raise ValueError(f"status must be one of: {allowed}")
        return v.lower()


# ── InventoryImport ────────────────────────────────────────

class InventoryImport(BaseModel):
    """库存变动导入校验"""
    model_config = ConfigDict(str_strip_whitespace=True)

    sku: Annotated[str, Field(min_length=1, max_length=64)]
    type: Annotated[str, Field(description="in / out / adjust / return")]
    quantity: Annotated[int, Field(gt=0, description="变动数量必须为正数")]
    related_order: str | None = None
    location: str | None = None
    operator: str | None = None
    note: str | None = None
    occurred_at: str | datetime | None = None

    @field_validator("type")
    @classmethod
    def type_must_be_valid(cls, v: str) -> str:
        allowed = {"in", "out", "adjust", "return"}
        if v.lower() not in allowed:
            raise ValueError(f"type must be one of: {allowed}")
        return v.lower()

    @field_validator("occurred_at", mode="before")
    @classmethod
    def parse_date(cls, v: str | datetime | None) -> datetime | None:
        return parse_datetime(v)


# ── TransactionImport ─────────────────────────────────────

class TransactionImport(BaseModel):
    """财务流水导入校验"""
    model_config = ConfigDict(str_strip_whitespace=True)

    order_id: str | None = None
    sku: str | None = None
    type: Annotated[str, Field(description="sale / refund / fee / shipping / adjustment")]
    amount: float
    currency: str = "USD"
    amount_usd: float | None = None
    exchange_rate: float | None = None
    date: str | datetime | None = None
    category: str | None = None
    note: str | None = None

    @field_validator("type")
    @classmethod
    def type_must_be_valid(cls, v: str) -> str:
        allowed = {"sale", "refund", "fee", "shipping", "adjustment"}
        if v.lower() not in allowed:
            raise ValueError(f"type must be one of: {allowed}")
        return v.lower()

    @field_validator("currency")
    @classmethod
    def currency_must_be_valid(cls, v: str) -> str:
        v = v.upper()
        try:
            Currency(v)
        except ValueError:
            raise ValueError(f"currency must be one of: {[c.value for c in Currency]}")
        return v

    @field_validator("date", mode="before")
    @classmethod
    def parse_date(cls, v: str | datetime | None) -> datetime | None:
        return parse_datetime(v)


# ── 批量校验 ──────────────────────────────────────────────

class ImportResult(BaseModel):
    """批量导入结果"""
    success: list[dict]
    errors: list[dict]  # {"index": int, "data": dict, "errors": list[str]}


def validate_batch(
    schema_class: type[BaseModel],
    records: list[dict],
) -> ImportResult:
    """
    批量校验数据，返回成功/失败列表。
    不 crash，收集所有错误。
    """
    success: list[dict] = []
    errors: list[dict] = []

    for i, record in enumerate(records):
        try:
            validated = schema_class.model_validate(record)
            success.append(validated.model_dump())
        except ValidationError as e:
            error_msgs = [f"{err['loc']}: {err['msg']}" for err in e.errors()]
            errors.append({"index": i, "data": record, "errors": error_msgs})
        except Exception as e:
            errors.append({"index": i, "data": record, "errors": [str(e)]})

    return ImportResult(success=success, errors=errors)
