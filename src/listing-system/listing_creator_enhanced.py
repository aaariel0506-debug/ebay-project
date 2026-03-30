#!/usr/bin/env python3
"""
Listing 创建流程编排（增强版）
Inventory Item → Offer → (可选) Publish

新增功能：
- 更多商品属性（颜色、尺寸、材质、型号、产地等）
- EAN/ISBN 支持
- 数量折扣
- 处理时间配置
- 配送地区/排除地区配置
- 促销运费
"""

import json
import logging
from dataclasses import dataclass
from typing import Optional, Dict, Any
import pandas as pd
from ebay_client import EbayClient, ApiResponse

logger = logging.getLogger("listing_creator")


@dataclass
class ListingResult:
    """单个 Listing 的创建结果"""
    sku: str
    success: bool = False
    offer_id: str = ""
    listing_id: str = ""
    error: str = ""
    step_failed: str = ""

    @property
    def status_text(self):
        if self.success:
            return "SUCCESS"
        return f"FAILED@{self.step_failed}"


class ListingCreatorEnhanced:
    """Listing 创建器（增强版）"""

    def __init__(self, client: EbayClient):
        self.client = client

    def create_listing(self, item: dict, auto_publish: bool = False) -> ListingResult:
        """
        创建完整 Listing（InventoryItem + Offer，可选 Publish）

        Args:
            item: 商品数据 dict
            auto_publish: 是否自动发布

        Returns:
            ListingResult
        """
        sku = str(item.get("sku", "")).strip()
        result = ListingResult(sku=sku)

        # Step 1: 创建 InventoryItem
        logger.info(f"[{sku}] Step 1: 创建 InventoryItem")
        inv_resp = self._create_inventory_item(item)
        if not inv_resp.ok:
            result.error = f"InventoryItem 创建失败：{inv_resp.error}"
            result.step_failed = "inventory_item"
            logger.error(f"[{sku}] {result.error}")
            return result

        logger.info(f"[{sku}] InventoryItem 创建成功 (HTTP {inv_resp.status_code})")

        # Step 2: 创建 Offer
        logger.info(f"[{sku}] Step 2: 创建 Offer")
        offer_resp = self._create_offer(item)
        if not offer_resp.ok:
            result.error = f"Offer 创建失败：{offer_resp.error}"
            result.step_failed = "offer"
            logger.error(f"[{sku}] {result.error}")
            return result

        result.offer_id = offer_resp.offer_id
        logger.info(f"[{sku}] Offer 创建成功，offer_id={result.offer_id}")

        # 如果没拿到 offer_id（沙盒常见问题）
        if not result.offer_id:
            logger.warning(f"[{sku}] API 未返回 offer_id，尝试通过查询获取...")
            result.offer_id = self._find_offer_by_sku(sku)

        # Step 3: 可选 - 发布
        if auto_publish and result.offer_id:
            logger.info(f"[{sku}] Step 3: 发布 Offer {result.offer_id}")
            pub_resp = self._publish_offer(result.offer_id)
            if pub_resp.ok:
                result.listing_id = pub_resp.listing_id
                logger.info(f"[{sku}] 发布成功！listing_id={result.listing_id}")
            else:
                result.error = f"发布失败：{pub_resp.error}"
                result.step_failed = "publish"
                logger.error(f"[{sku}] {result.error}")
                return result
        elif not auto_publish:
            logger.info(f"[{sku}] 已创建为草稿 (UNPUBLISHED)")

        result.success = True
        return result

    # ─── 内部方法 ──────────────────────────────────────

    def _create_inventory_item(self, item: dict):
        """创建/更新 InventoryItem（增强版）"""
        sku = item["sku"]

        # 构建 product
        product = {
            "title": str(item.get("title", "")),
            "description": str(item.get("description", "")),
            "aspects": {},
        }

        # 图片
        image_urls = str(item.get("image_urls", ""))
        urls = [u.strip() for u in image_urls.split(",") if u.strip()]
        if urls:
            product["imageUrls"] = urls

        # Aspects - 基础属性
        brand = str(item.get("brand", "")).strip()
        if brand:
            product["aspects"]["Brand"] = [brand]

        mpn = str(item.get("mpn", "")).strip()
        if mpn:
            product["aspects"]["MPN"] = [mpn]

        # Aspects - 增强属性
        color = str(item.get("color", "")).strip()
        if color:
            product["aspects"]["Color"] = [color]

        size = str(item.get("size", "")).strip()
        if size:
            product["aspects"]["Size"] = [size]

        material = str(item.get("material", "")).strip()
        if material:
            product["aspects"]["Material"] = [material]

        model = str(item.get("model", "")).strip()
        if model:
            product["aspects"]["Model"] = [model]

        country = str(item.get("country_of_manufacture", "")).strip()
        if country:
            product["aspects"]["Country/Region of Manufacture"] = [country]

        item_type = str(item.get("item_type", "")).strip()
        if item_type:
            product["aspects"]["Type"] = [item_type]

        series = str(item.get("series", "")).strip()
        if series:
            product["aspects"]["Series"] = [series]

        # UPC
        upc = item.get("upc", "")
        if isinstance(upc, float):
            upc = "" if pd.isna(upc) else str(int(upc))
        upc = str(upc).strip()
        if upc and upc.lower() not in ['', 'nan', 'none', 'null']:
            product["upc"] = [upc]

        # EAN
        ean = str(item.get("ean", "")).strip()
        if ean and ean.lower() not in ['', 'nan', 'none', 'null']:
            product["ean"] = [ean]

        # ISBN
        isbn = str(item.get("isbn", "")).strip()
        if isbn and isbn.lower() not in ['', 'nan', 'none', 'null']:
            product["isbn"] = [isbn]

        # 构建请求体
        body = {
            "product": product,
            "condition": self._get_condition(item),
            "availability": {
                "shipToLocationAvailability": {
                    "quantity": int(item.get("quantity", 1))
                }
            },
        }

        # 包装尺寸/重量
        pkg = self._build_package_info(item)
        if pkg:
            body["packageWeightAndSize"] = pkg

        return self.client.put(
            f"/sell/inventory/v1/inventory_item/{sku}", data=body
        )

    def _create_offer(self, item: dict):
        """创建 Offer（增强版）"""
        sku = item["sku"]

        # 基础定价
        pricing_summary = {
            "price": {
                "value": str(item.get("price", "0")),
                "currency": self.client.currency,
            }
        }

        # 数量折扣
        quantity_discount = item.get("quantity_discount")
        if quantity_discount:
            try:
                discounts = quantity_discount if isinstance(quantity_discount, list) else json.loads(quantity_discount)
                pricing_summary["quantityDiscountPricing"] = {
                    "quantityDiscountType": "VOLUME_PRICING",
                    "quantityDiscountTiers": [
                        {
                            "minimumQuantity": int(d.get("quantity", 2)),
                            "price": {
                                "value": str(float(item.get("price", 0)) * (1 - d.get("discount_percent", 0) / 100)),
                                "currency": self.client.currency
                            }
                        }
                        for d in discounts
                    ]
                }
                logger.info(f"[{sku}] 设置数量折扣：{len(discounts)} 档")
            except Exception as e:
                logger.warning(f"[{sku}] 数量折扣解析失败：{e}")

        body = {
            "sku": sku,
            "marketplaceId": self.client.marketplace_id,
            "format": self.client.config.get("listing_defaults", {}).get("format", "FIXED_PRICE"),
            "categoryId": str(item.get("category_id", "")),
            "pricingSummary": pricing_summary,
            "listingDescription": str(item.get("description", "")),
        }

        # 副标题
        subtitle = str(item.get("subtitle", "")).strip()
        if subtitle:
            body["title"] = subtitle

        # 业务策略
        if self.client.payment_policy_id:
            body["listingPolicies"] = body.get("listingPolicies", {})
            body["listingPolicies"]["paymentPolicyId"] = self.client.payment_policy_id
        if self.client.fulfillment_policy_id:
            body["listingPolicies"] = body.get("listingPolicies", {})
            body["listingPolicies"]["fulfillmentPolicyId"] = self.client.fulfillment_policy_id
        if self.client.return_policy_id:
            body["listingPolicies"] = body.get("listingPolicies", {})
            body["listingPolicies"]["returnPolicyId"] = self.client.return_policy_id

        # 仓库位置
        if self.client.merchant_location_key:
            body["merchantLocationKey"] = self.client.merchant_location_key

        # 处理时间
        handling_time = item.get("handling_time")
        if handling_time:
            body["fulfillmentStartEndDate"] = body.get("fulfillmentStartEndDate", {})
            body["fulfillmentStartEndDate"]["handlingTime"] = {
                "value": int(handling_time),
                "unit": "DAY"
            }
            logger.info(f"[{sku}] 设置处理时间：{handling_time} 天")

        # 配送地区
        ship_to_locations = item.get("ship_to_locations")
        if ship_to_locations:
            if isinstance(ship_to_locations, str):
                locations = [loc.strip() for loc in ship_to_locations.split(",")]
            else:
                locations = ship_to_locations
            body["fulfillmentStartEndDate"] = body.get("fulfillmentStartEndDate", {})
            body["fulfillmentStartEndDate"]["shipToLocations"] = [
                {"regionCode": loc} for loc in locations
            ]
            logger.info(f"[{sku}] 设置配送地区：{len(locations)} 个")

        # 排除地区
        exclude_locations = item.get("exclude_ship_to_locations")
        if exclude_locations:
            if isinstance(exclude_locations, str):
                locations = [loc.strip() for loc in exclude_locations.split(",")]
            else:
                locations = exclude_locations
            body["fulfillmentStartEndDate"] = body.get("fulfillmentStartEndDate", {})
            body["fulfillmentStartEndDate"]["excludeShipToLocations"] = [
                {"regionCode": loc} for loc in locations
            ]
            logger.info(f"[{sku}] 设置排除地区：{len(locations)} 个")

        resp = self.client.post("/sell/inventory/v1/offer", data=body)
        
        # Offer 已存在处理
        if not resp.ok and resp.body and isinstance(resp.body, dict):
            errors = resp.body.get('errors', [])
            for err in errors:
                if err.get('errorId') == 25002:
                    params = err.get('parameters', [])
                    for param in params:
                        if param.get('name') == 'offerId':
                            offer_id = param.get('value')
                            logger.info(f"Offer 已存在，offer_id={offer_id}")
                            return ApiResponse(200, {'offerId': offer_id}, {}, '')
        
        return resp

    def _publish_offer(self, offer_id: str):
        """发布 Offer"""
        return self.client.post(f"/sell/inventory/v1/offer/{offer_id}/publish")

    def _find_offer_by_sku(self, sku: str) -> str:
        """通过 SKU 查找 offerId"""
        resp = self.client.get(f"/sell/inventory/v1/offer?sku={sku}&limit=1")
        if resp.ok and isinstance(resp.body, dict):
            offers = resp.body.get("offers", [])
            if offers:
                return offers[0].get("offerId", "")
        return ""

    def _get_condition(self, item: dict) -> str:
        """获取 condition enum"""
        from data_validator import VALID_CONDITIONS
        cond = str(item.get("condition", "NEW")).strip().upper()
        if cond in VALID_CONDITIONS:
            return cond
        for enum_val, id_val in VALID_CONDITIONS.items():
            if id_val == cond:
                return enum_val
        return "NEW"

    def _build_package_info(self, item: dict) -> Optional[dict]:
        """构建包裹尺寸重量信息"""
        pkg = {}

        weight = item.get("weight_kg")
        if weight:
            try:
                pkg["weight"] = {
                    "value": float(weight),
                    "unit": "KILOGRAM",
                }
            except (ValueError, TypeError):
                pass

        length = item.get("length_cm")
        width = item.get("width_cm")
        height = item.get("height_cm")
        if all([length, width, height]):
            try:
                pkg["dimensions"] = {
                    "length": float(length),
                    "width": float(width),
                    "height": float(height),
                    "unit": "CENTIMETER",
                }
            except (ValueError, TypeError):
                pass

        return pkg if pkg else None
