"""
ListingTemplate CRUD + 应用逻辑。

提供模板的创建、查询、更新、删除，以及：
  - apply_template()  ：模板 + 商品数据 → ListingCreateRequest
  - from_existing()    ：从 eBay 已有 listing 拉取配置，保存为模板
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from core.database.connection import get_session
from core.ebay_api.exceptions import EbayApiError
from core.models.template import ListingTemplate
from loguru import logger as log

if TYPE_CHECKING:
    from core.models.product import Product
    from modules.listing.schemas import (
        ListingCreateRequest,
    )


class TemplateError(Exception):
    """模板操作失败。"""
    pass


class TemplateService:
    """Listing 模板服务。"""

    # ── CRUD ─────────────────────────────────────────────────────────────────

    def create_template(
        self,
        name: str,
        description_template: str | None = None,
        *,
        category_id: str | None = None,
        condition: str | None = None,
        condition_description: str | None = None,
        shipping_policy_id: str | None = None,
        return_policy_id: str | None = None,
        payment_policy_id: str | None = None,
        default_price_markup: float | None = None,
        image_settings: dict[str, Any] | None = None,
        is_default: bool = False,
        notes: str | None = None,
        currency: str = "USD",
        marketplace_id: str = "EBAY_US",
    ) -> ListingTemplate:
        """创建新模板。名称唯一。

        Args:
            name: 模板名称，唯一标识。
            description_template: 商品描述模板，支持占位符
                {title}, {brand}, {size}, {color}, {condition}, {price}。
            default_price_markup: 加价率，如 1.2 表示在成本价基础上 ×1.2。
            currency: 模板默认币种（USD/JPY 等）。
            marketplace_id: 模板默认市场（EBAY_US / EBAY_JP 等）。

        Returns:
            创建的 ListingTemplate 实例。
        """
        with get_session() as sess:
            existing = sess.query(ListingTemplate).filter(
                ListingTemplate.name == name
            ).first()
            if existing:
                raise TemplateError(f"模板名称 '{name}' 已存在")

            if is_default:
                # 取消其他默认模板
                sess.query(ListingTemplate).filter(
                    ListingTemplate.is_default == True  # noqa: E712
                ).update({"is_default": False})

            tpl = ListingTemplate(
                name=name,
                description_template=description_template,
                category_id=category_id,
                condition=condition,
                condition_description=condition_description,
                shipping_policy_id=shipping_policy_id,
                return_policy_id=return_policy_id,
                payment_policy_id=payment_policy_id,
                default_price_markup=default_price_markup,
                image_settings=image_settings,
                is_default=is_default,
                notes=notes,
            )
            sess.add(tpl)
            sess.commit()
            sess.refresh(tpl)
            log.info(f"创建模板: {tpl.name} (id={tpl.id})")
            return tpl

    def list_templates(
        self,
        include_disabled: bool = False,
    ) -> list[ListingTemplate]:
        """列出所有模板。

        Args:
            include_disabled: 是否包含已禁用的模板。
        """
        with get_session() as sess:
            q = sess.query(ListingTemplate)
            return list(q.all())

    def get_template(self, template_id: str) -> ListingTemplate:
        """按 ID 获取模板。"""
        with get_session() as sess:
            tpl = sess.query(ListingTemplate).filter(
                ListingTemplate.id == template_id
            ).first()
            if not tpl:
                raise TemplateError(f"模板不存在: {template_id}")
            return tpl

    def get_default_template(self) -> ListingTemplate | None:
        """获取默认模板（is_default=True），无则返回 None。"""
        with get_session() as sess:
            return sess.query(ListingTemplate).filter(
                ListingTemplate.is_default == True  # noqa: E712
            ).first()

    def update_template(
        self,
        template_id: str,
        *,
        name: str | None = None,
        description_template: str | None = None,
        category_id: str | None = None,
        condition: str | None = None,
        condition_description: str | None = None,
        shipping_policy_id: str | None = None,
        return_policy_id: str | None = None,
        payment_policy_id: str | None = None,
        default_price_markup: float | None = None,
        image_settings: dict[str, Any] | None = None,
        is_default: bool | None = None,
        notes: str | None = None,
    ) -> ListingTemplate:
        """更新模板字段（仅更新提供的非 None 字段）。"""
        with get_session() as sess:
            tpl = sess.query(ListingTemplate).filter(
                ListingTemplate.id == template_id
            ).first()
            if not tpl:
                raise TemplateError(f"模板不存在: {template_id}")

            if name is not None:
                tpl.name = name
            if description_template is not None:
                tpl.description_template = description_template
            if category_id is not None:
                tpl.category_id = category_id
            if condition is not None:
                tpl.condition = condition
            if condition_description is not None:
                tpl.condition_description = condition_description
            if shipping_policy_id is not None:
                tpl.shipping_policy_id = shipping_policy_id
            if return_policy_id is not None:
                tpl.return_policy_id = return_policy_id
            if payment_policy_id is not None:
                tpl.payment_policy_id = payment_policy_id
            if default_price_markup is not None:
                tpl.default_price_markup = default_price_markup
            if image_settings is not None:
                tpl.image_settings = image_settings
            if is_default is not None:
                if is_default:
                    sess.query(ListingTemplate).filter(
                        ListingTemplate.is_default == True,  # noqa: E712
                        ListingTemplate.id != template_id
                    ).update({"is_default": False})
                tpl.is_default = is_default
            if notes is not None:
                tpl.notes = notes

            sess.commit()
            sess.refresh(tpl)
            log.info(f"更新模板: {tpl.name} (id={tpl.id})")
            return tpl

    def delete_template(self, template_id: str) -> None:
        """删除模板。"""
        with get_session() as sess:
            tpl = sess.query(ListingTemplate).filter(
                ListingTemplate.id == template_id
            ).first()
            if not tpl:
                raise TemplateError(f"模板不存在: {template_id}")
            sess.delete(tpl)
            sess.commit()
            log.info(f"删除模板: {template_id}")

    # ── 应用模板 ────────────────────────────────────────────────────────────

    def apply_template(
        self,
        template_id: str,
        product: Product,
        *,
        price: float,
        quantity: int,
        condition: str | None = None,
        image_urls: list[str] | None = None,
        variant_specifics: list[Any] | None = None,
        title: str | None = None,
    ) -> ListingCreateRequest:
        """将模板应用到商品数据，生成 ListingCreateRequest。

        Args:
            template_id: 模板 ID。
            product: Product ORM 实例（包含 sku, title, brand 等）。
            price: 售价（必须是最终售价，不是成本价）。
            quantity: 可用数量。
            condition: 商品新旧程度，不填则用模板默认值。
            image_urls: 图片 URL 列表，覆盖模板配置。
            variant_specifics: 变体规格列表（用于变体 listing）。
            title: 商品标题，不填则用 product.title。

        Returns:
            ListingCreateRequest，可直接传给 ListingService.create_single_listing()。
        """
        from modules.listing.schemas import ListingCreateRequest

        tpl = self.get_template(template_id)

        # 占位符替换
        resolved_title = title or (getattr(product, "title", None) or str(product))
        brand = getattr(product, "brand", None) or ""

        description: str | None = None
        if tpl.description_template:
            # 尝试从 variant_specifics 提取 size/color
            size_val, color_val = "", ""
            if variant_specifics:
                for spec in variant_specifics:
                    name = str(getattr(spec, "name", "") or "")
                    value = str(getattr(spec, "value", "") or "")
                    if name.lower() == "size":
                        size_val = value
                    elif name.lower() == "color":
                        color_val = value

            description = tpl.apply_placeholder(
                title=resolved_title,
                brand=brand,
                size=size_val,
                color=color_val,
                condition=condition or tpl.condition or "",
                price=str(price),
            )

        # 图片
        picture_urls: list[str] = []
        if image_urls:
            picture_urls = image_urls
        elif tpl.image_settings:
            secondary = tpl.image_settings.get("secondary_urls", [])
            if secondary and isinstance(secondary, list):
                picture_urls = secondary

        # 使用 ListingCreateRequest（主 schema）
        resolved_condition = condition if condition is not None else (tpl.condition or "NEW")

        return ListingCreateRequest(
            sku=product.sku,
            title=resolved_title,
            description=description or "",
            category_id=tpl.category_id or "",
            condition=resolved_condition,
            condition_description=tpl.condition_description,
            listing_price=price,
            quantity=quantity,
            image_urls=picture_urls,
            fulfillment_policy_id=tpl.shipping_policy_id or "",
            return_policy_id=tpl.return_policy_id or "",
            payment_policy_id=tpl.payment_policy_id or "",
            currency=tpl.currency or "USD",
            marketplace_id=tpl.marketplace_id or "EBAY_US",
        )

    # ── 从现有 listing 生成模板 ─────────────────────────────────────────────

    def from_existing(
        self,
        *,
        sku: str | None = None,
        item_id: str | None = None,
        template_name: str,
        client: Any | None = None,
    ) -> ListingTemplate:
        """从 eBay 已有 listing 拉取配置，保存为模板。

        双路径策略：
        1. 优先 Inventory API（需要 SKU）：GET /sell/inventory/v1/inventory_item/{sku}
           → 返回库存详情，含关联的 offer（可拿到 policies）
        2. Fallback Browse API（需要 Item ID）：GET /buy/browse/v1/item/{item_id}
           → 返回 listing 公开信息（不含 policies，需手动补充）

        注意：Offer ID ≠ Item ID。Item ID 是买家看到的编号，Offer ID 是内部编号。
        要用 Inventory API 必须提供 SKU。

        Args:
            sku: 商品 SKU（用于 Inventory API 路径，可拿到完整 policies）。
            item_id: eBay Item ID（用于 Browse API fallback，仅返回公开信息）。
            template_name: 保存为模板的名称。
            client: EbayClient 实例，不传则用默认。

        Returns:
            新创建的 ListingTemplate。
        """
        if client is None:
            from core.ebay_api import EbayClient
            client = EbayClient()

        resp: dict[str, Any] = {}
        source: str = ""

        # 路径 1：Inventory API（需要 SKU）
        if sku:
            try:
                resp = client.get(
                    f"/sell/inventory/v1/inventory_item/{sku}",
                )
                source = "inventory_api"
            except EbayApiError:
                resp = {}
            except Exception:
                resp = {}

        # 路径 2：Browse API（需要 Item ID）
        if not resp and item_id:
            try:
                resp = client.get(
                    f"/buy/browse/v1/item/{item_id}",
                )
                source = "browse_api"
            except EbayApiError as exc:
                raise TemplateError(
                    f"无法获取 listing（SKU={sku}, Item ID={item_id}）。"
                    f"Inventory API 和 Browse API 均失败: {exc}"
                ) from exc

        if not resp:
            raise TemplateError(
                "无法获取 listing：未提供有效的 SKU 或 Item ID"
            )

        # 提取字段（两个 API 响应格式不同）
        if source == "inventory_api":
            # Inventory API: 字段在根级别
            category_id = str(resp.get("product", {}).get("categoryId", "") or "")
            condition = str(resp.get("condition", "") or "")
            condition_desc = str(resp.get("conditionDescription", "") or "")
            description_template: str | None = None
            if resp.get("product", {}).get("description"):
                description_template = str(resp["product"]["description"])
            policies = resp.get("listingPolicies", {}) or {}
            payment_policy_id = str(policies.get("paymentPolicyId", "") or "")
            return_policy_id = str(policies.get("returnPolicyId", "") or "")
            fulfillment_policy_id = str(policies.get("fulfillmentPolicyId", "") or "")
        else:
            # Browse API: categoryId 在 additionalImageUrls 等位置
            category_id = str(resp.get("categoryId", "") or "")
            condition = str(resp.get("condition", "") or "")
            condition_desc = str(resp.get("conditionDescription", "") or resp.get("shortDescription", "") or "")
            description_template = None  # Browse API 不返回完整 description
            # Browse API 不返回 policies，需要用户手动填写
            payment_policy_id = ""
            return_policy_id = ""
            fulfillment_policy_id = ""

        return self.create_template(
            name=template_name,
            description_template=description_template,
            category_id=category_id,
            condition=condition,
            condition_description=condition_desc,
            shipping_policy_id=fulfillment_policy_id,
            return_policy_id=return_policy_id,
            payment_policy_id=payment_policy_id,
        )
