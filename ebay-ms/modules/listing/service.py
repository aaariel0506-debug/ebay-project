"""modules.listing.service — ListingService，eBay Listing 创建/更新业务逻辑"""
from typing import Any

from core.database.connection import get_session
from core.ebay_api.client import EbayClient
from core.ebay_api.exceptions import EbayApiError
from core.events.bus import get_event_bus
from core.models import EbayListing, ListingStatus, Product
from core.utils.logger import get_logger
from modules.listing import schemas as ls
from modules.listing.schemas import (
    ImageUploadResponse,
    InventoryItemGroupRequest,
    InventoryItemResponse,
    ListingCreateRequest,
    ListingCreateResponse,
    VariantItem,
    VariantListingCreateResponse,
)
from modules.listing.utils import (
    build_inventory_availability,
    build_inventory_item_group,
    build_offers_pricing_summary,
    build_variant_payload,
    extract_listing_id_from_href,
    normalize_condition,
    validate_image_files,
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
        offer_id: str | None = None
        listing_id: str | None = None
        ebay_item_id: str | None = None

        # ── Step 1: createOrReplaceInventoryItem ─────────
        try:
            self._create_inventory_item(req)
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

        self.client.put(
            "/sell/inventory/v1/inventory_item/{sku}".format(sku=req.sku),
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

        resp = self.client.post("/sell/inventory/v1/offer", json_body=body)
        offer_id = resp.get("offerId")
        if not offer_id:
            raise ListingCreateError("createOffer", "响应中没有 offerId", resp)
        return offer_id

    def _publish_offer(self, offer_id: str) -> str:
        """Step 3: POST /offer/{offer_id}/publish → 返回 listing_id"""
        resp = self.client.post(f"/sell/inventory/v1/offer/{offer_id}/publish", json_body={})
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
            self.client.delete(f"/sell/inventory/v1/inventory_item/{sku}")
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


    # ── Variant Listing ───────────────────────────────────────

    def create_variant_listing(
        self, req: InventoryItemGroupRequest
    ) -> VariantListingCreateResponse:
        """
        创建变体 Listing（多变体多 offer）。

        流程：
          1. 为每个 VariantItem 调用 createOrReplaceInventoryItem
          2. 创建 InventoryItemGroup（关联所有变体）
          3. 为每个变体创建 Offer
          4. 发布所有 Offer
          5. DB 写入（多记录）+ 事件发布

        失败策略：
          - Step 1 失败：返回错误（无回滚）
          - Step 2 失败：回滚所有 Step 1 创建的 inventory items
          - Step 3 失败：回滚 Step 2 + 所有 Step 1
          - Step 4 失败：记录失败的 offer，不回滚成功部分
        """

        variants_created: list[dict] = []
        errors: list[str] = []
        skus_created: list[str] = []
        group_id: str | None = None

        log.info(f"开始创建变体 Listing: {len(req.variants)} 个变体")

        # ── Step 1: 创建每个变体的 InventoryItem ───────────
        for variant in req.variants:
            try:
                payload = self._build_variant_inventory_payload(variant, req)
                self.client.put(
                    f"/sell/inventory/v1/inventory_item/{variant.sku}",
                    json_body=payload,
                )
                skus_created.append(variant.sku)
                log.info(f"Step 1 完成: variant sku={variant.sku}")
            except EbayApiError as exc:
                log.error(f"Step 1 失败 sku={variant.sku}: {exc}")
                errors.append(f"inventory_item({variant.sku}): {exc}")
                # 回滚已创建的
                self._rollback_inventory_items(skus_created)
                return ls.VariantListingCreateResponse(
                    success=False,
                    errors=errors,
                )

        # ── Step 2: 创建 InventoryItemGroup ───────────────
        # group_key = first variant SKU (eBay recommended pattern for multi-variant listings)
        group_key = req.variants[0].sku
        try:
            group_payload = self._build_inventory_item_group_payload(req)
            # PUT /sell/inventory/v1/inventory_item_group/{inventoryItemGroupKey}
            group_resp = self.client.put(
                f"/sell/inventory/v1/inventory_item_group/{group_key}",
                json_body=group_payload,
            )
            group_id = group_resp.get("groupId") or group_key
            log.info(f"Step 2 完成: group_key={group_key}")
        except EbayApiError as exc:
            log.error(f"Step 2 失败 (InventoryItemGroup): {exc}")
            errors.append(f"inventory_item_group: {exc}")
            self._rollback_inventory_items(skus_created)
            return ls.VariantListingCreateResponse(success=False, errors=errors)

        # ── Step 3: 为每个变体创建 Offer ───────────────────
        offer_ids: list[str | None] = []
        for variant in req.variants:
            try:
                offer_id = self._create_variant_offer(variant, req)
                offer_ids.append(offer_id)
                variants_created.append({
                    "sku": variant.sku,
                    "offer_id": offer_id,
                    "status": "OFFER_CREATED",
                })
                log.info(f"Step 3 完成: variant sku={variant.sku}, offer_id={offer_id}")
            except EbayApiError as exc:
                log.error(f"Step 3 失败 sku={variant.sku}: {exc}")
                errors.append(f"create_offer({variant.sku}): {exc}")
                offer_ids.append(None)

        # ── Step 4: 批量发布所有 Offers（publishOfferByInventoryItemGroup） ──
        # eBay API: POST /sell/inventory/v1/offer/publish_by_inventory_item_group/{inventoryItemGroupKey}
        # 一条 API 调用把该 group 下所有未发布的 offer 全部上线
        try:
            publish_resp = self.client.post(
                f"/sell/inventory/v1/offer/publish_by_inventory_item_group/{group_key}",
                json_body={},
            )
            # publishResp 返回 all listingIds for the group
            listings_map = publish_resp.get("listingId", [])
            if isinstance(listings_map, dict):
                # Some responses return a mapping
                pass
            log.info(f"Step 4 完成: group_key={group_key}")
        except EbayApiError as exc:
            log.error(f"Step 4 失败 (publishOfferByInventoryItemGroup): {exc}")
            errors.append(f"publish_by_group: {exc}")
            # Mark all as publish failed (individual listingIds unavailable)
            for i in range(len(req.variants)):
                if offer_ids[i] is not None:
                    variants_created[i]["status"] = "PUBLISH_FAILED"

        # ── Step 5: DB 写入 + 事件发布 ──────────────────────
        try:
            self._save_variant_records(req, variants_created, group_id)
        except Exception as exc:
            log.error(f"DB 写入失败: {exc}")
            errors.append(f"db_write: {exc}")

        try:
            self._event_bus.publish(
                "LISTING_CREATED",
                payload={
                    "group_id": group_id,
                    "variant_count": len(req.variants),
                    "skus": [v.sku for v in req.variants],
                    "type": "variant",
                },
            )
        except Exception as exc:
            log.warning(f"事件发布失败（非阻塞）: {exc}")

        return ls.VariantListingCreateResponse(
            success=len(errors) == 0,
            group_id=group_id,
            variants=variants_created,
            errors=errors,
        )

    def _build_variant_inventory_payload(
        self, variant: VariantItem, req: InventoryItemGroupRequest
    ) -> dict:
        """为单个变体构建 createOrReplaceInventoryItem payload"""
        specifics = [{"name": s.name, "value": s.value} for s in variant.variant_specifics]
        return build_variant_payload(
            sku=variant.sku,
            price=variant.price,
            quantity=variant.quantity,
            condition=variant.condition,
            variant_specifics=specifics,
            image_urls=variant.image_urls or req.image_urls,
            currency=req.currency,
        )

    def _build_inventory_item_group_payload(
        self, req: InventoryItemGroupRequest
    ) -> dict:
        """构建 InventoryItemGroup 请求体"""

        body = {
            "group_title": req.group_title,
            "group_description": req.group_description,
            "brand": req.brand,
            "category_id": req.category_id,
            "condition": req.condition,
            "image_urls": req.image_urls,
            "variants": [
                {
                    "variant_specifics": [
                        {"name": s.name, "value": s.value}
                        for s in v.variant_specifics
                    ]
                }
                for v in req.variants
            ],
        }
        return build_inventory_item_group(body)

    def _create_variant_offer(
        self, variant: VariantItem, req: InventoryItemGroupRequest
    ) -> str:
        """为单个变体创建 Offer"""
        from modules.listing.utils import build_offers_pricing_summary

        body: dict[str, Any] = {
            "sku": variant.sku,
            "marketplaceId": req.marketplace_id,
            "format": "FIXED_PRICE",
            "availableQuantity": variant.quantity,
            "listingDescription": req.group_description or req.group_title,
            "pricingSummary": build_offers_pricing_summary(variant.price, req.currency),
        }
        policies: dict[str, str] = {}
        if req.fulfillment_policy_id:
            policies["fulfillmentPolicyId"] = req.fulfillment_policy_id
        if req.return_policy_id:
            policies["returnPolicyId"] = req.return_policy_id
        if req.payment_policy_id:
            policies["paymentPolicyId"] = req.payment_policy_id
        if policies:
            body["listingPolicies"] = policies

        resp = self.client.post("/sell/inventory/v1/offer", json_body=body)
        offer_id = resp.get("offerId")
        if not offer_id:
            raise ListingCreateError("createVariantOffer", f"响应中无 offerId: {resp}", {})
        return offer_id

    def _publish_variant_offer(self, offer_id: str) -> str:
        """发布单个变体 Offer"""
        resp = self.client.post(f"/sell/inventory/v1/offer/{offer_id}/publish", json_body={})
        listing_id = resp.get("listingId")
        if not listing_id:
            raise ListingCreateError("publishVariantOffer", f"响应中无 listingId: {resp}", {})
        return listing_id

    def _rollback_inventory_items(self, skus: list[str]) -> None:
        """回滚：删除已创建的 inventory items"""
        for sku in skus:
            try:
                self.client.delete(f"/sell/inventory/v1/inventory_item/{sku}")
                log.info(f"Rollback: 已删除 inventory_item/{sku}")
            except Exception as exc:
                log.warning(f"Rollback 失败 sku={sku}: {exc}")

    def _save_variant_records(
        self,
        req: InventoryItemGroupRequest,
        variants: list[dict],
        group_id: str | None,
    ) -> None:
        """写入所有变体的 EbayListing + Product 记录"""
        with get_session() as s:
            for i, variant in enumerate(req.variants):
                info = variants[i]
                listing = EbayListing(
                    ebay_item_id=info.get("listing_id") or f"group-{group_id}-{variant.sku}",
                    sku=variant.sku,
                    title=req.group_title,
                    listing_price=variant.price,
                    quantity_available=variant.quantity,
                    status=ListingStatus.ACTIVE if info.get("status") == "ACTIVE" else ListingStatus.DRAFT,
                )
                s.add(listing)

                product = s.query(Product).filter_by(sku=variant.sku).first()
                if not product:
                    product = Product(
                        sku=variant.sku,
                        title=req.group_title or variant.sku,
                        cost_price=0.0,
                        cost_currency="USD",
                        status="active",
                    )
                    s.add(product)

            s.commit()

    # ── 图片上传 / 校验 ──────────────────────────────────

    def validate_images(self, paths: list[str]) -> ImageUploadResponse:
        """
        校验图片（本地文件或 URL）。
        不上传到 eBay，只校验格式/大小，返回可提交给 eBay 的 URL 列表。
        eBay Inventory API 接受外部 URL，无需中转上传。
        """

        valid_urls, raw_results = validate_image_files(paths)

        results = [
            ls.ImageValidationResult(
                path=r["path"],
                valid=r["valid"],
                error=r.get("error"),
                size_bytes=r.get("size_bytes"),
                format=r.get("format"),
            )
            for r in raw_results
        ]

        return ls.ImageUploadResponse(
            total=len(paths),
            valid_count=sum(1 for r in results if r.valid),
            invalid_count=sum(1 for r in results if not r.valid),
            accepted_urls=valid_urls,
            results=results,
        )

    def list_listings(
        self,
        *,
        status: str | None = None,
        sku: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list:
        """Query EbayListing records."""
        from core.database.connection import get_session
        from core.models import EbayListing, ListingStatus

        with get_session() as sess:
            q = sess.query(EbayListing)
            if status:
                try:
                    st = ListingStatus(status)
                    q = q.filter(EbayListing.status == st)
                except ValueError:
                    q = q.filter(EbayListing.status == status)
            if sku:
                q = q.filter(EbayListing.sku == sku)
            q = q.order_by(EbayListing.created_at.desc())
            q = q.offset(offset).limit(limit)
            return list(q.all())

    def get_listing(self, ebay_item_id: str):
        """Fetch a single EbayListing by ebay_item_id."""
        from core.database.connection import get_session

        with get_session() as sess:
            return sess.query(EbayListing).filter(
                EbayListing.ebay_item_id == ebay_item_id
            ).first()
