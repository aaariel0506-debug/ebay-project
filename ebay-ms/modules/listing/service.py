"""modules.listing.service — ListingService，eBay Listing 创建/更新业务逻辑"""
from typing import Any

from loguru import logger

from core.ebay_api.client import EbayClient
from core.ebay_api.exceptions import EbayApiError
from core.events.bus import get_event_bus
from core.models import EbayListing, Product, ListingStatus
from core.database.connection import get_session
from core.utils.logger import get_logger
from modules.listing.schemas import (
    ListingCreateRequest,
    ListingCreateResponse,
    InventoryItemResponse,
    OfferResponse,
    PublishResponse,
)
from modules.listing.utils import (
    normalize_condition,
    build_inventory_availability,
    build_offers_pricing_summary,
    extract_listing_id_from_href,
    format_price,
)

log = get_logger("listing_service")


class ListingCreateError(Exception):
    """Listing 创建失败，包含失败步骤和原因"""

    def __init__(self, step: str, message: str, details: dict | None = None):
        self.step = step
        self.message = message
        self.details = details or {}
        super().__init__(f"[{step}] {message}")


class ListingService:
    """
    eBay Listing 服务

    核心流程（3 步）：
        Step 1: createOrReplaceInventoryItem  →  PUT /inventory_item/{sku}
        Step 2: createOffer                   →  POST /offer
        Step 3: publishOffer                  →  POST /offer/{offer_id}/publish
    """

    def __init__(self, client: EbayClient | None = None):
        self.client = client or EbayClient()
        self._event_bus = get_event_bus()

    # ── 公开接口 ──────────────────────────────────────────

    def create_single_listing(self, req: ListingCreateRequest) -> ListingCreateResponse:
        """
        创建单个 Listing（3 步合一，自动处理回滚）

        成功时：
          - 在 EbayListing 表写入记录
          - 在 Product 表更新/写入关联记录
          - 发布 LISTING_CREATED 事件
        """
        log.info(f"开始创建 Listing: sku={req.sku}, price={req.listing_price}")

        errors: list[str] = []
        inventory_done = False
        offer_created = False
        offer_id: str | None = None
        listing_id: str | None = None
        ebay_item_id: str | None = None

        # ── Step 1: createOrReplaceInventoryItem ─────────
        try:
            self._create_inventory_item(req)
            inventory_done = True
            log.info(f"Step 1 完成: sku={req.sku}")
        except EbayApiError as exc:
            log.error(f"Step 1 失败 (createOrReplaceInventoryItem): {exc}")
            errors.append(f"inventory_item: {exc}")
            return ListingCreateResponse(
                success=False,
                sku=req.sku,
                errors=errors,
            )

        # ── Step 2: createOffer ─────────────────────────
        try:
            offer_id = self._create_offer(req)
            offer_created = True
            log.info(f"Step 2 完成: offer_id={offer_id}")
        except EbayApiError as exc:
            log.error(f"Step 2 失败 (createOffer): {exc}")
            errors.append(f"create_offer: {exc}")
            # 回滚 Step 1
            self._rollback_inventory_item(req.sku)
            return ListingCreateResponse(
                success=False,
                sku=req.sku,
                errors=errors,
            )

        # ── Step 3: publishOffer ────────────────────────
        try:
            listing_id = self._publish_offer(offer_id)
            log.info(f"Step 3 完成: listing_id={listing_id}")
        except EbayApiError as exc:
            log.error(f"Step 3 失败 (publishOffer): {exc}")
            errors.append(f"publish_offer: {exc}")
            # 记录 offer 已创建但不生效，保留 offer_id 供调试
            return ListingCreateResponse(
                success=False,
                sku=req.sku,
                offer_id=offer_id,
                errors=errors,
            )

        # ── 成功：写入数据库 ────────────────────────────
        ebay_item_id = listing_id
        try:
            self._save_listing_record(
                ebay_item_id=ebay_item_id,
                sku=req.sku,
                title=req.title,
                price=req.listing_price,
                quantity=req.quantity,
                status=ListingStatus.ACTIVE,
            )
            log.info(f"DB 记录已写入: ebay_item_id={ebay_item_id}")
        except Exception as exc:
            log.error(f"DB 写入失败（Listing 已创建）: {exc}")
            errors.append(f"db_write: {exc}")

        # ── 发布事件 ────────────────────────────────────
        try:
            self._event_bus.publish(
                "LISTING_CREATED",
                payload={
                    "ebay_item_id": ebay_item_id,
                    "sku": req.sku,
                    "title": req.title,
                    "price": req.listing_price,
                    "marketplace_id": req.marketplace_id,
                },
            )
        except Exception as exc:
            log.warning(f"事件发布失败（非阻塞）: {exc}")

        return ListingCreateResponse(
            success=True,
            ebay_item_id=ebay_item_id,
            offer_id=offer_id,
            sku=req.sku,
            status="ACTIVE",
            errors=errors if errors else [],
        )

    # ── 内部方法 ─────────────────────────────────────────

    def _create_inventory_item(self, req: ListingCreateRequest) -> InventoryItemResponse:
        """Step 1: PUT /inventory_item/{sku}"""
        body = {
            "sku": req.sku,
            "availability": build_inventory_availability(req.quantity),
            "condition": normalize_condition(req.condition),
            "product": req.product if hasattr(req, "product") else None,
        }
        if req.condition_description:
            body["condition_description"] = req.condition_description
        if req.image_urls:
            body["imageUrls"] = req.image_urls

        # Remove None values
        body = {k: v for k, v in body.items() if v is not None}

        resp = self.client.put(
            "/inventory_item/{sku}".format(sku=req.sku),
            json_body=body,
        )
        return InventoryItemResponse(sku=req.sku, status="inventory_item_created")

    def _create_offer(self, req: ListingCreateRequest) -> str:
        """Step 2: POST /offer → 返回 offer_id"""
        body: dict[str, Any] = {
            "sku": req.sku,
            "marketplaceId": req.marketplace_id,
            "format": "FIXED_PRICE",
            "availableQuantity": req.quantity,
            "listingDescription": req.description or req.title,
            "pricingSummary": build_offers_pricing_summary(req.listing_price, req.currency),
        }

        # 合并 listing policies
        policies: dict[str, Any] = {}
        if req.fulfillment_policy_id:
            policies["fulfillmentPolicyId"] = req.fulfillment_policy_id
        if req.return_policy_id:
            policies["returnPolicyId"] = req.return_policy_id
        if req.payment_policy_id:
            policies["paymentPolicyId"] = req.payment_policy_id
        if policies:
            body["listingPolicies"] = policies

        resp = self.client.post("/offer", json_body=body)
        offer_id = resp.get("offerId")
        if not offer_id:
            raise ListingCreateError("createOffer", "响应中没有 offerId", resp)
        return offer_id

    def _publish_offer(self, offer_id: str) -> str:
        """Step 3: POST /offer/{offer_id}/publish → 返回 listing_id"""
        resp = self.client.post(f"/offer/{offer_id}/publish", json_body={})
        listing_id = (
            resp.get("listingId")
            or extract_listing_id_from_href(resp.get("listingIdHref"))
            or resp.get("listingId")
        )
        if not listing_id:
            raise ListingCreateError("publishOffer", "响应中没有 listingId", resp)
        return listing_id

    def _rollback_inventory_item(self, sku: str) -> None:
        """回滚：删除已创建的 inventory item"""
        try:
            self.client.delete(f"/inventory_item/{sku}")
            log.info(f"Rollback Step 1 完成: 已删除 inventory_item/{sku}")
        except Exception as exc:
            log.warning(f"Rollback Step 1 失败（已尽力）: {exc}")

    def _save_listing_record(
        self,
        ebay_item_id: str,
        sku: str,
        title: str | None,
        price: float,
        quantity: int,
        status: ListingStatus,
    ) -> None:
        """写入 EbayListing + 更新 Product 表"""
        with get_session() as s:
            # 写入或更新 Listing 记录
            existing = s.query(EbayListing).filter_by(ebay_item_id=ebay_item_id).first()
            if not existing:
                listing = EbayListing(
                    ebay_item_id=ebay_item_id,
                    sku=sku,
                    title=title,
                    listing_price=price,
                    quantity_available=quantity,
                    status=status,
                )
                s.add(listing)

            # 确保 Product 存在
            product = s.query(Product).filter_by(sku=sku).first()
            if not product:
                product = Product(
                    sku=sku,
                    title=title or "Imported from eBay",
                    cost_price=0.0,
                    cost_currency="USD",
                    status="active",
                )
                s.add(product)

            s.commit()
