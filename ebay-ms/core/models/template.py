"""ListingTemplate ORM model — 保存常用 listing 配置为模板，实现一键复用。"""

from __future__ import annotations

import uuid
from typing import Any

from core.models.base import Base, TimestampMixin
from sqlalchemy import JSON, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column


class ListingTemplate(TimestampMixin, Base):
    """保存常用的 listing 配置模板。

    模板中的 description_template 支持占位符：
      {title}       → 商品标题
      {brand}       → 品牌
      {size}        → 尺码
      {color}       → 颜色
      {condition}   → 商品新旧程度
      {price}       → 价格

    apply_template() 会自动替换这些占位符。
    """

    __tablename__ = "listing_templates"

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )
    name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        unique=True,
        index=True,
    )
    description_template: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )
    category_id: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
    )
    condition: Mapped[str | None] = mapped_column(
        String(30),
        nullable=True,
    )
    condition_description: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )
    shipping_policy_id: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )
    return_policy_id: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )
    payment_policy_id: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )
    currency: Mapped[str | None] = mapped_column(
        String(3),
        nullable=True,
        default="USD",
        comment="模板默认币种",
    )
    marketplace_id: Mapped[str | None] = mapped_column(
        String(20),
        nullable=True,
        default="EBAY_US",
        comment="模板默认市场，如 EBAY_US / EBAY_JP",
    )
    default_price_markup: Mapped[float | None] = mapped_column(
        Numeric(6, 2),
        nullable=True,
        comment="加价率，如 1.2 表示在成本价基础上加价 20%",
    )
    image_settings: Mapped[dict[str, Any] | None] = mapped_column(
        JSON,
        nullable=True,
        comment="图片配置：{primary_index, secondary_urls, watermark_enabled}",
    )
    is_default: Mapped[bool] = mapped_column(
        default=False,
        nullable=False,
    )
    notes: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    def __repr__(self) -> str:
        return f"<ListingTemplate {self.name}>"

    def apply_placeholder(
        self,
        title: str,
        brand: str | None = None,
        size: str | None = None,
        color: str | None = None,
        condition: str | None = None,
        price: str | None = None,
    ) -> str | None:
        """将 description_template 中的占位符替换为实际值。"""
        if self.description_template is None:
            return None
        result = self.description_template
        for placeholder, value in {
            "{title}": title,
            "{brand}": brand or "",
            "{size}": size or "",
            "{color}": color or "",
            "{condition}": condition or "",
            "{price}": price or "",
        }.items():
            result = result.replace(placeholder, str(value))
        return result
