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


    # ── 出库 ───────────────────────────────────────────

    p_out = sub.add_parser("outbound", help="出库记录")
    p_out.add_argument("--sku", required=True, help="商品 SKU")
    p_out.add_argument("--quantity", required=True, type=int, help="出库数量")
    p_out.add_argument("--order", dest="related_order", help="关联订单号")
    p_out.add_argument("--operator", help="操作人")
    p_out.add_argument("--location", help="出库库位")
    p_out.add_argument("--note", help="备注")

    p_ret = sub.add_parser("return-in", help="退货入库")
    p_ret.add_argument("--sku", required=True)
    p_ret.add_argument("--quantity", required=True, type=int)
    p_ret.add_argument("--order", dest="related_order", help="关联订单号")
    p_ret.add_argument("--operator", help="操作人")
    p_ret.add_argument("--note", help="备注")

    p_out_list = sub.add_parser("outbound-list", help="查询出库记录")
    p_out_list.add_argument("--sku", help="按 SKU 筛选")
    p_out_list.add_argument("--order", dest="related_order", help="按订单号筛选")
    p_out_list.add_argument("--date-from", dest="start_date", help="开始日期（YYYY-MM-DD）")
    p_out_list.add_argument("--date-to", dest="end_date", help="结束日期（YYYY-MM-DD）")
    p_out_list.add_argument("--limit", type=int, default=100)

    # stocktake 子命令
    p_stk_start = sub.add_parser("stocktake-start", help="开始新盘点")
    p_stk_start.add_argument("--skus", help="要盘点的 SKU 列表（逗号分隔，默认全部）")
    p_stk_start.add_argument("--operator", help="操作人")

    p_stk_record = sub.add_parser("stocktake-record", help="录入实际清点数量")
    p_stk_record.add_argument("--id", required=True, type=int, dest="stocktake_id", help="盘点单 ID")
    p_stk_record.add_argument(
        "--file", type=Path, required=True,
        help="清点数据 CSV，格式：sku,actual_quantity[,note]",
    )

    p_stk_finish = sub.add_parser("stocktake-finish", help="结束盘点并生成调整记录")
    p_stk_finish.add_argument("--id", required=True, type=int, dest="stocktake_id", help="盘点单 ID")

    p_stk_list = sub.add_parser("stocktake-list", help="列出现有盘点单")
    p_stk_list.add_argument("--status", choices=["in_progress", "finished", "cancelled"])
    p_stk_list.add_argument("--limit", type=int, default=50)

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
    if args.cmd == "outbound":
        return _cmd_outbound(args)
    if args.cmd == "return-in":
        return _cmd_return_in(args)
    if args.cmd == "outbound-list":
        return _cmd_outbound_list(args)
    if args.cmd == "stocktake-start":
        return _cmd_stocktake_start(args)
    if args.cmd == "stocktake-record":
        return _cmd_stocktake_record(args)
    if args.cmd == "stocktake-finish":
        return _cmd_stocktake_finish(args)
    if args.cmd == "stocktake-list":
        return _cmd_stocktake_list(args)

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



def _cmd_outbound(args) -> int:
    from modules.inventory_offline import InboundService

    svc = InboundService()
    result = svc.outbound(
        sku=args.sku,
        quantity=args.quantity,
        related_order=args.related_order,
        operator=args.operator,
        location=args.location,
        note=args.note,
    )
    print(
        f"✅ 出库记录: {result['sku']} × {result['quantity']}"
        f"，剩余库存: {result['remaining_stock']}"
    )
    return 0


def _cmd_return_in(args) -> int:
    from modules.inventory_offline import InboundService

    svc = InboundService()
    result = svc.return_inventory(
        sku=args.sku,
        quantity=args.quantity,
        related_order=args.related_order,
        operator=args.operator,
        note=args.note,
    )
    print(f"✅ 退货入库: {result['sku']} × {result['quantity']}")
    return 0


def _cmd_outbound_list(args) -> int:
    from datetime import datetime

    from modules.inventory_offline import InboundService

    svc = InboundService()

    # 解析日期参数
    start_date = None
    end_date = None
    if args.start_date:
        start_date = datetime.strptime(args.start_date, "%Y-%m-%d")
    if args.end_date:
        end_date = datetime.strptime(args.end_date, "%Y-%m-%d")

    rows = svc.list_outbound(
        sku=args.sku,
        related_order=args.related_order,
        start_date=start_date,
        end_date=end_date,
        limit=args.limit,
    )

    if not rows:
        print("（无出库记录）")
        return 0

    print(
        f"{'时间':<26}  {'SKU':<20}  {'数量':>5}  {'订单':<15}  {'操作人'}"
    )
    print("-" * 85)
    for r in rows:
        ts = r["occurred_at"].strftime("%Y-%m-%d %H:%M:%S") if r["occurred_at"] else "—"
        print(
            f"{ts:<26}  {r['sku']:<20}  {r['quantity']:>5}  "
            f"{r['related_order'] or '—':<15}  {r['operator'] or '—'}"
        )
    print(f"\n共 {len(rows)} 条")
    return 0


def _cmd_stocktake_start(args) -> int:
    from modules.inventory_offline.stocktake_service import StocktakeService

    skus = args.skus.split(",") if args.skus else None
    svc = StocktakeService()
    result = svc.start_stocktake(skus=skus, operator=args.operator)
    print(f"✅ 创建盘点单 #{result['stocktake_id']}，{result['items_count']} 个 SKU，已锁定系统库存")
    return 0


def _cmd_stocktake_record(args) -> int:
    import csv

    from modules.inventory_offline.stocktake_service import StocktakeService

    counts = {}
    with open(args.file, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            counts[row["sku"].strip()] = int(row["actual_quantity"].strip())

    svc = StocktakeService()
    result = svc.record_count(stocktake_id=args.stocktake_id, counts=counts)

    print(f"✅ 录入 {result['items_updated']} 项，{len(result['differences'])} 项有差异：")
    for d in result["differences"]:
        print(f"   {d['sku']}: 系统{d['system']} → 实际{d['actual']}，差异 {d['diff']:+d}")
    return 0


def _cmd_stocktake_finish(args) -> int:
    from modules.inventory_offline.stocktake_service import StocktakeService

    svc = StocktakeService()
    result = svc.finish_stocktake(stocktake_id=args.stocktake_id)

    print(
        f"✅ 盘点单 #{result.stocktake_id} 已结束："
        f"{result.items_count} 项已清点，"
        f"{result.adjustment_records} 条调整记录，"
        f"总差异 {result.total_difference:+d}"
    )
    return 0


def _cmd_stocktake_list(args) -> int:
    from modules.inventory_offline.stocktake_service import StocktakeService

    svc = StocktakeService()
    rows = svc.list_stocktakes(status=args.status, limit=args.limit)

    if not rows:
        print("（无盘点单）")
        return 0

    print(f"{'ID':>4}  {'状态':<12}  {'开始时间':<26}  {'结束时间':<26}  {'操作人'}")
    print("-" * 90)
    for r in rows:
        started = r["started_at"].strftime("%Y-%m-%d %H:%M") if r["started_at"] else "—"
        finished = r["finished_at"].strftime("%Y-%m-%d %H:%M") if r["finished_at"] else "—"
        print(
            f"{r['id']:>4}  {r['status']:<12}  {started:<26}  {finished:<26}  {r['operator'] or '—'}"
        )
    print(f"\n共 {len(rows)} 条")
    return 0


if __name__ == "__main__":
    sys.exit(run_inventory_offline_cmd(sys.argv[1:]))
