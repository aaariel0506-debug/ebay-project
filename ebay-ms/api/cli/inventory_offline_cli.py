"""api/cli/inventory_offline_cli.py

Day 19: inventory offline 子命令
- inbound-create / inbound-confirm / inbound-list / inbound-cancel
- stock / stock-all
"""

import sys
from pathlib import Path


def run_inventory_offline_cmd(argv: list[str]) -> int:
    import argparse

    parser = argparse.ArgumentParser(prog="main.py inventory offline")
    sub = parser.add_subparsers(dest="cmd", help="子命令")

    # ── 入库单管理 ──────────────────────────────────

    p_create = sub.add_parser("inbound-create", help="创建入库单")
    p_create.add_argument("--supplier", required=True, help="供应商名称")
    p_create.add_argument(
        "--file", type=Path, required=True,
        help="CSV 文件路径，格式：sku,expected_quantity,cost_price[,note]",
    )
    p_create.add_argument("--receipt-no", help="入库单号（默认自动生成）")
    p_create.add_argument("--operator", help="操作人")
    p_create.add_argument("--note", help="备注")

    p_confirm = sub.add_parser("inbound-confirm", help="到货确认")
    p_confirm.add_argument("--receipt-id", required=True, type=int, help="入库单 ID")
    p_confirm.add_argument(
        "--file", type=Path, required=True,
        help="收货明细 CSV，格式：sku,received_quantity[,note]",
    )
    p_confirm.add_argument("--operator", help="操作人")
    p_confirm.add_argument("--location", help="存放库位")

    p_list = sub.add_parser("inbound-list", help="列出入库单")
    p_list.add_argument("--status", choices=["pending", "shipped", "partial", "received", "cancelled"])
    p_list.add_argument("--supplier", help="供应商筛选")
    p_list.add_argument("--limit", type=int, default=50)

    p_cancel = sub.add_parser("inbound-cancel", help="取消入库单")
    p_cancel.add_argument("--receipt-id", required=True, type=int, help="入库单 ID")

    # ── 库存查询 ───────────────────────────────────

    p_stock = sub.add_parser("stock", help="查询 SKU 当前库存")
    p_stock.add_argument("sku", help="商品 SKU")

    p_stock_all = sub.add_parser("stock-all", help="查询所有 SKU 库存快照")
    p_stock_all.add_argument("--limit", type=int, default=200, help="最多返回 SKU 数")

    args = parser.parse_args(argv)

    # ── 路由 ───────────────────────────────────────

    if args.cmd == "inbound-create":
        return _cmd_inbound_create(args)
    if args.cmd == "inbound-confirm":
        return _cmd_inbound_confirm(args)
    if args.cmd == "inbound-list":
        return _cmd_inbound_list(args)
    if args.cmd == "inbound-cancel":
        return _cmd_inbound_cancel(args)
    if args.cmd == "stock":
        return _cmd_stock(args)
    if args.cmd == "stock-all":
        return _cmd_stock_all(args)

    parser.print_help()
    return 0


# ── 命令实现 ──────────────────────────────────────────────

def _cmd_inbound_create(args) -> int:
    import csv

    from modules.inventory_offline import InboundItemInput, InboundService

    rows = []
    with open(args.file, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows.append(
                InboundItemInput(
                    sku=row["sku"].strip(),
                    expected_quantity=int(row["expected_quantity"].strip()),
                    cost_price=float(row["cost_price"].strip()),
                    note=row.get("note", "").strip() or None,
                )
            )

    svc = InboundService()
    result = svc.create_receipt(
        supplier=args.supplier,
        items=rows,
        receipt_no=args.receipt_no,
        operator=args.operator,
        note=args.note,
    )
    print(f"✅ 创建入库单 {result.receipt_no}，{result.item_count} 个 SKU，状态: {result.status}")
    return 0


def _cmd_inbound_confirm(args) -> int:
    import csv

    from modules.inventory_offline import InboundService, ReceivedItemInput

    rows = []
    with open(args.file, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows.append(
                ReceivedItemInput(
                    sku=row["sku"].strip(),
                    received_quantity=int(row["received_quantity"].strip()),
                    note=row.get("note", "").strip() or None,
                )
            )

    svc = InboundService()
    result = svc.confirm_inbound(
        receipt_id=args.receipt_id,
        received_items=rows,
        operator=args.operator,
        location=args.location,
    )
    print(
        f"✅ 入库确认 {result.receipt_no}："
        f"{result.items_confirmed} 项确认，"
        f"{result.total_received} 件入库，"
        f"状态: {result.status}"
    )
    return 0


def _cmd_inbound_list(args) -> int:
    from modules.inventory_offline import InboundService

    svc = InboundService()
    receipts = svc.list_receipts(status=args.status, supplier=args.supplier, limit=args.limit)

    if not receipts:
        print("（无入库单）")
        return 0

    print(f"{'ID':>4}  {'单号':<25}  {'供应商':<15}  {'状态':<10}  {'操作人'}")
    print("-" * 80)
    for r in receipts:
        print(
            f"{r['id']:>4}  {r['receipt_no']:<25}  {r['supplier']:<15}  "
            f"{r['status']:<10}  {r['operator'] or '—'}"
        )
    print(f"\n共 {len(receipts)} 条")
    return 0


def _cmd_inbound_cancel(args) -> int:
    from modules.inventory_offline import InboundService

    svc = InboundService()
    result = svc.cancel_receipt(receipt_id=args.receipt_id)
    print(f"✅ 取消入库单 {result['receipt_no']}，状态: {result['status']}")
    return 0


def _cmd_stock(args) -> int:
    from modules.inventory_offline import InboundService

    svc = InboundService()
    stock = svc.get_stock(args.sku)

    print(f"SKU: {stock['sku']}")
    print(f"可用库存: {stock['available_quantity']}")
    print(f"  总入库: {stock['total_in']}")
    print(f"  总出库: {stock['total_out']}")
    print(f"  调整:   {stock['total_adjust']}")
    print(f"  退货:   {stock['total_return']}")
    if stock["location_breakdown"]:
        print("库位分布:")
        for loc, qty in stock["location_breakdown"].items():
            print(f"  {loc}: {qty}")
    if stock["last_movement_at"]:
        print(f"最近变动: {stock['last_movement_at']}")
    return 0


def _cmd_stock_all(args) -> int:
    from modules.inventory_offline import InboundService

    svc = InboundService()
    stocks = svc.get_all_stock(limit=args.limit)

    print(f"{'SKU':<20}  {'商品名':<30}  {'可用':>6}  {'入库':>6}  {'出库':>6}")
    print("-" * 80)
    for s in stocks:
        print(
            f"{s['sku']:<20}  {s['title'][:28]:<30}  "
            f"{s['available_quantity']:>6}  "
            f"{s['total_in']:>6}  "
            f"{s['total_out']:>6}"
        )
    print(f"\n共 {len(stocks)} 个 SKU")
    return 0


if __name__ == "__main__":
    sys.exit(run_inventory_offline_cmd(sys.argv[1:]))
