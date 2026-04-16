"""inventory_offline — 线下实体库存模块"""
from modules.inventory_offline.offline_inventory_service import (
    InboundItemInput,
    InboundReceiptResult,
    OfflineInventoryService,
    ReceivedItemInput,
)

__all__ = [
    "OfflineInventoryService",
    "InboundItemInput",
    "ReceivedItemInput",
    "InboundReceiptResult",
]
