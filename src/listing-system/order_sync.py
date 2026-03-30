#!/usr/bin/env python3
"""
eBay 订单同步工具
从 eBay 拉取订单数据，支持状态同步、物流单号回传

功能：
- 获取订单列表（按时间范围/状态过滤）
- 获取订单详情
- 标记发货（上传物流单号）
- 订单数据本地存储（Excel/JSON）
- 增量同步（基于上次同步时间）

涉及 API：
- GET /sell/fulfillment/v1/order - 订单列表
- GET /sell/fulfillment/v1/order/{order_id} - 订单详情
- POST /sell/fulfillment/v1/order/{order_id}/ship - 发货
"""

import json
import logging
from pathlib import Path
from datetime import datetime, timedelta
from typing import List, Optional, Dict, Any
from dataclasses import dataclass, asdict
from ebay_client import EbayClient

logger = logging.getLogger("order_sync")


@dataclass
class OrderInfo:
    """订单信息"""
    order_id: str
    order_number: str  # eBay 订单号
    create_date: str
    payment_status: str
    fulfillment_status: str
    total_amount: float
    currency: str
    buyer_username: str
    buyer_email: str = ""
    
    # 商品明细
    line_items: List[Dict[str, Any]] = None
    
    # 收货地址
    ship_to_address: Dict[str, str] = None
    
    # 物流信息
    shipping_carrier: str = ""
    tracking_number: str = ""
    ship_date: str = ""
    
    # 本地处理状态
    synced_at: str = ""
    local_status: str = "pending"  # pending, shipped, archived


class OrderSync:
    """eBay 订单同步器"""

    def __init__(self, client: EbayClient, storage_path: str = None):
        """
        Args:
            client: EbayClient 实例
            storage_path: 本地存储路径（默认 ./orders/）
        """
        self.client = client
        self.storage_path = Path(storage_path or Path(__file__).parent / "orders")
        self.storage_path.mkdir(exist_ok=True)
        
        # 状态文件（记录上次同步时间）
        self.state_file = self.storage_path / "sync_state.json"
        self.state = self._load_state()
        
        logger.info(f"订单同步器初始化完成 | 存储路径：{self.storage_path}")

    def _load_state(self) -> Dict[str, Any]:
        """加载同步状态"""
        if self.state_file.exists():
            with open(self.state_file, "r") as f:
                return json.load(f)
        return {
            "last_sync_time": None,
            "total_orders_synced": 0
        }

    def _save_state(self):
        """保存同步状态"""
        with open(self.state_file, "w") as f:
            json.dump(self.state, f, indent=2)

    def get_orders(
        self,
        start_date: str = None,
        end_date: str = None,
        status: str = None,
        limit: int = 100
    ) -> List[OrderInfo]:
        """
        获取订单列表

        Args:
            start_date: 开始日期 (ISO 8601 格式，如 "2026-03-01T00:00:00Z")
            end_date: 结束日期
            status: 订单状态过滤 (UNPAID, PAID, SHIPPED, CANCELLED 等)
            limit: 最大返回数量

        Returns:
            List[OrderInfo]
        """
        # 默认时间范围：过去 30 天
        if not start_date:
            if self.state.get("last_sync_time"):
                start_date = self.state["last_sync_time"]
            else:
                start_date = (datetime.now() - timedelta(days=30)).isoformat() + "Z"
        
        if not end_date:
            end_date = datetime.now().isoformat() + "Z"

        logger.info(f"获取订单：{start_date} 至 {end_date}")

        # 构建查询参数
        params = {
            "orderCreateDateFrom": start_date,
            "orderCreateDateTo": end_date,
            "limit": min(limit, 200),  # API 最大 200
            "sort": "create_date_asc"
        }

        if status:
            params["fulfillmentStatus"] = status

        # 发送请求
        resp = self.client.get("/sell/fulfillment/v1/order", data=params)

        if not resp.ok:
            logger.error(f"获取订单失败：{resp.status_code} {resp.error}")
            return []

        orders = []
        order_list = resp.body.get("orders", [])

        for order_data in order_list:
            order = self._parse_order(order_data)
            orders.append(order)

        logger.info(f"获取到 {len(orders)} 个订单")

        # 更新同步状态
        if orders:
            self.state["last_sync_time"] = end_date
            self.state["total_orders_synced"] += len(orders)
            self._save_state()

        return orders

    def get_order_detail(self, order_id: str) -> Optional[OrderInfo]:
        """
        获取单个订单详情

        Args:
            order_id: eBay 订单 ID

        Returns:
            OrderInfo 或 None
        """
        logger.info(f"获取订单详情：{order_id}")

        resp = self.client.get(f"/sell/fulfillment/v1/order/{order_id}")

        if not resp.ok:
            logger.error(f"获取订单详情失败：{resp.status_code} {resp.error}")
            return None

        return self._parse_order(resp.body)

    def mark_shipped(
        self,
        order_id: str,
        carrier: str,
        tracking_number: str,
        ship_date: str = None
    ) -> bool:
        """
        标记订单为已发货

        Args:
            order_id: eBay 订单 ID
            carrier: 物流承运商（如 "USPS", "FEDEX", "JAPAN_POST"）
            tracking_number: 物流单号
            ship_date: 发货日期（默认当前时间）

        Returns:
            是否成功
        """
        logger.info(f"标记订单已发货：{order_id} | 承运商：{carrier} | 单号：{tracking_number}")

        if not ship_date:
            ship_date = datetime.now().isoformat() + "Z"

        # 构建发货请求
        ship_data = {
            "carrierCode": carrier,
            "trackingNumber": tracking_number,
            "shipDate": ship_date,
            "notifyBuyer": True  # 通知买家
        }

        resp = self.client.post(
            f"/sell/fulfillment/v1/order/{order_id}/ship",
            data=ship_data
        )

        if resp.ok:
            logger.info(f"订单 {order_id} 已标记为已发货")
            return True
        else:
            logger.error(f"标记发货失败：{resp.status_code} {resp.error}")
            return False

    def mark_shipped_japan_post(
        self,
        order_id: str,
        tracking_number: str,
        ship_date: str = None
    ) -> bool:
        """
        使用日本邮政标记发货（便捷方法）

        Args:
            order_id: eBay 订单 ID
            tracking_number: 物流单号
            ship_date: 发货日期

        Returns:
            是否成功
        """
        return self.mark_shipped(order_id, "JAPAN_POST", tracking_number, ship_date)

    def save_orders_to_excel(self, orders: List[OrderInfo], filename: str = None):
        """
        保存订单到 Excel

        Args:
            orders: 订单列表
            filename: 输出文件名（默认自动生成）
        """
        try:
            import openpyxl
            from openpyxl import Workbook
        except ImportError:
            logger.error("需要安装 openpyxl: pip install openpyxl --break-system-packages")
            return

        if not filename:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"eBay_orders_{timestamp}.xlsx"

        filepath = self.storage_path / filename

        logger.info(f"保存 {len(orders)} 个订单到 {filepath}")

        wb = Workbook()
        ws = wb.active
        ws.title = "Orders"

        # 表头
        headers = [
            "Order ID", "Order Number", "Create Date", "Payment Status",
            "Fulfillment Status", "Total Amount", "Currency", "Buyer",
            "Shipping Carrier", "Tracking Number", "Ship Date", "Synced At"
        ]
        ws.append(headers)

        # 数据行
        for order in orders:
            row = [
                order.order_id,
                order.order_number,
                order.create_date,
                order.payment_status,
                order.fulfillment_status,
                order.total_amount,
                order.currency,
                order.buyer_username,
                order.shipping_carrier,
                order.tracking_number,
                order.ship_date,
                order.synced_at
            ]
            ws.append(row)

        # 调整列宽
        for col in ws.columns:
            max_length = 0
            column = col[0].column_letter
            for cell in col:
                if cell.value:
                    max_length = max(max_length, len(str(cell.value)))
            ws.column_dimensions[column].width = min(max_length + 2, 50)

        wb.save(filepath)
        logger.info(f"订单已保存到 {filepath}")

    def save_orders_to_json(self, orders: List[OrderInfo], filename: str = None):
        """保存订单到 JSON"""
        if not filename:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"eBay_orders_{timestamp}.json"

        filepath = self.storage_path / filename

        data = {
            "synced_at": datetime.now().isoformat(),
            "count": len(orders),
            "orders": [asdict(o) for o in orders]
        }

        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

        logger.info(f"订单已保存到 {filepath}")

    # ─── 内部方法 ──────────────────────────────────────

    def _parse_order(self, data: Dict[str, Any]) -> OrderInfo:
        """解析订单数据"""
        # 基本信息
        order = OrderInfo(
            order_id=data.get("orderId", ""),
            order_number=data.get("orderNumber", ""),
            create_date=data.get("createDate", ""),
            payment_status=data.get("paymentStatus", ""),
            fulfillment_status=data.get("fulfillmentStatus", ""),
            total_amount=float(data.get("total", {}).get("value", 0)),
            currency=data.get("total", {}).get("currency", "USD"),
            buyer_username=data.get("buyer", {}).get("username", ""),
            buyer_email=data.get("buyer", {}).get("email", ""),
            synced_at=datetime.now().isoformat()
        )

        # 商品明细
        line_items = []
        for item in data.get("lineItems", []):
            line_items.append({
                "item_id": item.get("lineItemId", ""),
                "sku": item.get("sku", ""),
                "title": item.get("title", ""),
                "quantity": item.get("quantity", 1),
                "price": item.get("sellingStatus", {}).get("total", {}).get("value", 0),
                "currency": item.get("sellingStatus", {}).get("total", {}).get("currency", "USD")
            })
        order.line_items = line_items

        # 收货地址
        ship_to = data.get("shipTo", {})
        order.ship_to_address = {
            "name": ship_to.get("recipientName", ""),
            "line1": ship_to.get("primaryAddress", {}).get("addressLine1", ""),
            "line2": ship_to.get("primaryAddress", {}).get("addressLine2", ""),
            "city": ship_to.get("primaryAddress", {}).get("city", ""),
            "state": ship_to.get("primaryAddress", {}).get("stateOrProvince", ""),
            "postal_code": ship_to.get("primaryAddress", {}).get("postalCode", ""),
            "country": ship_to.get("primaryAddress", {}).get("countryCode", ""),
            "phone": ship_to.get("primaryAddress", {}).get("phoneNumber", "")
        }

        # 物流信息
        shipping_detail = data.get("fulfillmentStartEndDate", {})
        if shipping_detail.get("shipDate"):
            order.ship_date = shipping_detail["shipDate"]

        for shipment in data.get("shipments", []):
            if shipment.get("trackingNumber"):
                order.tracking_number = shipment["trackingNumber"]
            if shipment.get("shippingCarrierCode"):
                order.shipping_carrier = shipment["shippingCarrierCode"]

        return order

    def get_sync_status(self) -> Dict[str, Any]:
        """获取同步状态"""
        return {
            "last_sync_time": self.state.get("last_sync_time"),
            "total_orders_synced": self.state.get("total_orders_synced", 0),
            "storage_path": str(self.storage_path)
        }


# ─── 命令行工具 ──────────────────────────────────────

if __name__ == "__main__":
    import sys

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s"
    )

    print("=" * 60)
    print("📦 eBay 订单同步工具")
    print("=" * 60)

    # 初始化
    try:
        client = EbayClient()
        sync = OrderSync(client)
    except Exception as e:
        print(f"❌ 初始化失败：{e}")
        sys.exit(1)

    if len(sys.argv) < 2:
        print("\n用法:")
        print("  python3 order_sync.py sync              # 同步最近 30 天订单")
        print("  python3 order_sync.py sync --days 7     # 同步最近 7 天")
        print("  python3 order_sync.py detail <order_id> # 查看订单详情")
        print("  python3 order_sync.py ship <order_id> <carrier> <tracking>")
        print("  python3 order_sync.py status            # 查看同步状态")
        sys.exit(1)

    command = sys.argv[1]

    if command == "sync":
        # 解析参数
        days = 30
        if "--days" in sys.argv:
            idx = sys.argv.index("--days")
            if idx + 1 < len(sys.argv):
                days = int(sys.argv[idx + 1])

        start_date = (datetime.now() - timedelta(days=days)).isoformat() + "Z"
        orders = sync.get_orders(start_date=start_date)

        if orders:
            sync.save_orders_to_excel(orders)
            sync.save_orders_to_json(orders)
            print(f"\n✅ 同步完成：{len(orders)} 个订单")
        else:
            print("\n⚠️  没有新订单")

    elif command == "detail":
        if len(sys.argv) < 3:
            print("❌ 请提供订单 ID")
            sys.exit(1)

        order_id = sys.argv[2]
        order = sync.get_order_detail(order_id)

        if order:
            print(f"\n订单详情:")
            print(f"  Order ID: {order.order_id}")
            print(f"  Order Number: {order.order_number}")
            print(f"  创建时间：{order.create_date}")
            print(f"  支付状态：{order.payment_status}")
            print(f"  发货状态：{order.fulfillment_status}")
            print(f"  总金额：{order.total_amount} {order.currency}")
            print(f"  买家：{order.buyer_username}")
            print(f"  商品：{len(order.line_items)} 件")
            for item in order.line_items:
                print(f"    - {item['title']} x{item['quantity']} ${item['price']}")
        else:
            print(f"❌ 订单不存在：{order_id}")

    elif command == "ship":
        if len(sys.argv) < 5:
            print("❌ 用法：python3 order_sync.py ship <order_id> <carrier> <tracking>")
            sys.exit(1)

        order_id = sys.argv[2]
        carrier = sys.argv[3]
        tracking = sys.argv[4]

        success = sync.mark_shipped(order_id, carrier, tracking)
        if success:
            print(f"✅ 订单 {order_id} 已标记为已发货")
        else:
            print(f"❌ 标记发货失败")

    elif command == "status":
        status = sync.get_sync_status()
        print(f"\n同步状态:")
        print(f"  上次同步：{status['last_sync_time'] or '从未'}")
        print(f"  累计订单：{status['total_orders_synced']}")
        print(f"  存储路径：{status['storage_path']}")

    else:
        print(f"❌ 未知命令：{command}")
        sys.exit(1)
