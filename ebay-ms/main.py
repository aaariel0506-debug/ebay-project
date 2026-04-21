#!/usr/bin/env python3
"""
eBay Management System — 统一 CLI 入口

Usage:
    python main.py listing create --file products.csv
    python main.py listing list
    python main.py listing template list
    python main.py inventory online status
    python main.py inventory online price-check --file prices.csv
    python main.py --help
"""

import argparse
import sys


def _register_event_handlers() -> None:
    """进程启动时注册所有事件处理器（幂等）"""
    from core.events.bus import get_event_bus
    from modules.inventory_online.event_handlers import handle_stock_out

    bus = get_event_bus()
    bus.subscribe("STOCK_OUT", handle_stock_out)


def run() -> int:
    _register_event_handlers()
    parser = argparse.ArgumentParser(
        prog="main.py",
        description="eBay Management System",
    )
    sub = parser.add_subparsers(dest="module", help="模块")

    # ── listing 模块 ────────────────────────────────────────────────────────
    listing_p = sub.add_parser("listing", help="Listing 模块")
    listing_sub = listing_p.add_subparsers(dest="cmd", help="子命令")

    p_create = listing_sub.add_parser("create", help="创建 listing")
    p_create.add_argument("--file", help="CSV/XLSX 文件路径（批量上新）")
    p_create.add_argument("--sku", help="单品 SKU")
    p_create.add_argument("--template", dest="template_id", help="模板 ID")
    p_create.add_argument("--price", type=float, help="售价")
    p_create.add_argument("--quantity", type=int, default=1)
    p_create.add_argument("--batch-id", dest="batch_id")
    p_create.add_argument("--no-resume", action="store_true")

    p_list = listing_sub.add_parser("list", help="列出 listing")
    p_list.add_argument("--status")
    p_list.add_argument("--sku")
    p_list.add_argument("--limit", type=int, default=50)
    p_list.add_argument("--offset", type=int, default=0)

    p_tpl = listing_sub.add_parser("template", help="模板管理")
    p_tpl_sub = p_tpl.add_subparsers(dest="template_cmd")

    p_tpl_get = p_tpl_sub.add_parser("get", help="查看模板")
    p_tpl_get.add_argument("template_id")
    p_tpl_create = p_tpl_sub.add_parser("create", help="创建模板")
    p_tpl_create.add_argument("--name", required=True)
    p_tpl_create.add_argument("--description-template", dest="description_template")
    p_tpl_create.add_argument("--category-id", dest="category_id")
    p_tpl_create.add_argument("--condition", default="NEW")
    p_tpl_create.add_argument("--currency", default="USD")
    p_tpl_create.add_argument("--marketplace-id", dest="marketplace_id", default="EBAY_US")
    p_tpl_create.add_argument("--shipping-policy-id", dest="shipping_policy_id")
    p_tpl_create.add_argument("--return-policy-id", dest="return_policy_id")
    p_tpl_create.add_argument("--payment-policy-id", dest="payment_policy_id")
    p_tpl_create.add_argument("--default", dest="is_default", action="store_true")
    p_tpl_del = p_tpl_sub.add_parser("delete", help="删除模板")
    p_tpl_del.add_argument("template_id")

    p_imp = listing_sub.add_parser("import-template", help="生成导入模板")
    p_imp.add_argument("--output", "-o")
    _ = listing_sub.add_parser("status", help="查看状态")

    # ── inventory 模块 ─────────────────────────────────────────────────────
    inv_p = sub.add_parser("inventory", help="库存模块")
    inv_sub = inv_p.add_subparsers(dest="inv_cmd")

    # inventory online 子命令
    inv_online_p = inv_sub.add_parser("online", help="线上虚拟库存")
    inv_online_sub = inv_online_p.add_subparsers(dest="cmd")

    _ = inv_online_sub.add_parser("status", help="库存概览")
    _ = inv_online_sub.add_parser("alert", help="缺货/低库存预警")
    _ = inv_online_sub.add_parser("sync", help="从 eBay 同步 listing")
    p_price_check = inv_online_sub.add_parser("price-check", help="检查进货价变化")
    p_price_check.add_argument("--sku", help="单个 SKU")
    p_price_check.add_argument("--file", type=str, help="CSV 文件路径（批量）")
    p_price_check.add_argument("--threshold", type=float, default=0.10, help="价格变化阈值（默认 10%%）")
    p_price_check.add_argument("--min-margin", type=float, default=0.15, help="最低利润率阈值（默认 15%%）")

    inv_online_sub.add_parser("price-history", help="查看价格历史").add_argument("sku", help="SKU")
    p_margin = inv_online_sub.add_parser("margin-check", help="检查利润率低于阈值的商品")
    p_margin.add_argument("--threshold", type=float, default=0.15)
    inv_online_sub.add_parser("restock-advice", help="补货建议")
    p_adj = inv_online_sub.add_parser("adjust", help="调整 eBay 库存")
    inv_online_sub.add_parser("check-consistency", help="检测线上线下库存一致性")
    p_adj.add_argument("--sku", help="SKU")
    p_adj.add_argument("--quantity", type=int, help="新库存数量")
    p_adj.add_argument("--file", type=str, help="CSV 文件路径（批量）")
    p_adj.add_argument("--dry-run", action="store_true", help="模拟运行")

    # inventory offline 子命令
    inv_offline_p = inv_sub.add_parser("offline", help="线下实体库存")
    inv_offline_sub = inv_offline_p.add_subparsers(dest="cmd")

    p_ib_create = inv_offline_sub.add_parser("inbound-create", help="创建入库单")
    p_ib_create.add_argument("--supplier", required=True)
    p_ib_create.add_argument("--file", type=str, required=True)
    p_ib_create.add_argument("--receipt-no")
    p_ib_create.add_argument("--operator")
    p_ib_create.add_argument("--note")

    p_ib_confirm = inv_offline_sub.add_parser("inbound-confirm", help="到货确认")
    p_ib_confirm.add_argument("--receipt-id", required=True, type=int)
    p_ib_confirm.add_argument("--file", type=str, required=True)
    p_ib_confirm.add_argument("--operator")
    p_ib_confirm.add_argument("--location")

    p_ib_list = inv_offline_sub.add_parser("inbound-list", help="列出入库单")
    p_ib_list.add_argument("--status")
    p_ib_list.add_argument("--supplier")
    p_ib_list.add_argument("--limit", type=int, default=50)

    p_ib_cancel = inv_offline_sub.add_parser("inbound-cancel", help="取消入库单")
    p_ib_cancel.add_argument("--receipt-id", required=True, type=int)

    p_stk = inv_offline_sub.add_parser("stock", help="查询 SKU 当前库存")
    p_stk.add_argument("sku", help="商品 SKU")

    p_stk_all = inv_offline_sub.add_parser("stock-all", help="查询所有 SKU 库存快照")
    p_stk_all.add_argument("--limit", type=int, default=200)

    p_out = inv_offline_sub.add_parser("outbound", help="出库记录")
    p_out.add_argument("--sku", required=True)
    p_out.add_argument("--quantity", required=True, type=int)
    p_out.add_argument("--order", dest="related_order")
    p_out.add_argument("--operator")
    p_out.add_argument("--location")
    p_out.add_argument("--note")

    p_ret = inv_offline_sub.add_parser("return-in", help="退货入库")
    p_ret.add_argument("--sku", required=True)
    p_ret.add_argument("--quantity", required=True, type=int)
    p_ret.add_argument("--order", dest="related_order")
    p_ret.add_argument("--operator")
    p_ret.add_argument("--note")

    p_out_list = inv_offline_sub.add_parser("outbound-list", help="查询出库记录")
    p_out_list.add_argument("--sku")
    p_out_list.add_argument("--order", dest="related_order")
    p_out_list.add_argument("--date-from", dest="start_date")
    p_out_list.add_argument("--date-to", dest="end_date")
    p_out_list.add_argument("--limit", type=int, default=100)

    p_stk_start = inv_offline_sub.add_parser("stocktake-start", help="开始新盘点")
    p_stk_start.add_argument("--skus")
    p_stk_start.add_argument("--operator")

    p_stk_record = inv_offline_sub.add_parser("stocktake-record", help="录入实际清点数量")
    p_stk_record.add_argument("--id", required=True, type=int, dest="stocktake_id")
    p_stk_record.add_argument("--file", type=str, required=True)

    p_stk_finish = inv_offline_sub.add_parser("stocktake-finish", help="结束盘点并生成调整记录")
    p_stk_finish.add_argument("--id", required=True, type=int, dest="stocktake_id")

    p_stk_list = inv_offline_sub.add_parser("stocktake-list", help="列出现有盘点单")
    p_stk_list.add_argument("--status", choices=["in_progress", "finished", "cancelled"])
    p_stk_list.add_argument("--limit", type=int, default=50)
    inv_offline_sub.add_parser("report", help="导出库存报表（快照 / 出入库明细）")

    # ── finance 模块 ────────────────────────────────────────────────────────
    finance_p = sub.add_parser("finance", help="财务模块")
    finance_sub = finance_p.add_subparsers(dest="cmd", help="子命令")

    p_sync = finance_sub.add_parser("sync-orders", help="同步 eBay 订单")
    p_sync.add_argument("--date-from", dest="date_from", help="起始日期 YYYY-MM-DD")
    p_sync.add_argument("--date-to", dest="date_to", help="结束日期 YYYY-MM-DD")
    p_sync.add_argument("--full", action="store_true", help="全量同步（忽略日期范围）")

    p_link = finance_sub.add_parser("link-costs", help="补填历史 Transaction 成本")
    p_link.add_argument("--dry-run", action="store_true", default=False, help="模拟运行")
    p_link.add_argument("--since", dest="since", help="仅处理该日期之后的记录 YYYY-MM-DD")
    p_link.add_argument("--export", dest="export", help="导出 unlinked 订单到 xlsx 路径")

    p_unlinked = finance_sub.add_parser("unlinked-orders", help="列出无法关联成本的订单")
    p_unlinked.add_argument("--since", dest="since", help="YYYY-MM-DD")
    p_unlinked.add_argument("--export", dest="export", help="导出到 xlsx 路径")

    p_report = finance_sub.add_parser("report", help="Transaction 汇总报告（毛利/销售额）")
    p_report.add_argument(
        "--period",
        choices=["daily", "weekly", "monthly"],
        default="daily",
        help="汇总周期（默认 daily）",
    )
    p_report.add_argument("--year", type=int, dest="year", help="月度报表的年份")
    p_report.add_argument("--month", type=int, dest="month", help="月度报表的月份")

    args = parser.parse_args()

    if args.module is None:
        parser.print_help()
        return 0

    if args.module == "listing":
        from api.cli.listing_cli import run_listing_cmd
        return run_listing_cmd(sys.argv[2:] if len(sys.argv) > 2 else [])

    if args.module == "inventory":
        if getattr(args, "inv_cmd", None) == "offline":
            from api.cli.inventory_offline_cli import run_inventory_offline_cmd
            return run_inventory_offline_cmd(sys.argv[4:] if len(sys.argv) > 4 else [])
        from api.cli.inventory_online_cli import run_inventory_online_cmd
        return run_inventory_online_cmd(sys.argv[3:] if len(sys.argv) > 3 else [])

    if args.module == "finance":
        from core.database.connection import get_session
        from modules.finance.cost_linker import export_unlinked_xlsx, link_costs, list_unlinked_orders
        from modules.finance.order_sync_service import OrderSyncService
        from modules.finance.report import TransactionReport

        if args.cmd == "sync-orders":
            from datetime import datetime as dt

            from core.models import get_last_sync

            svc = OrderSyncService()

            if args.full:
                # 全量同步：从 2020-01-01 开始
                date_from = dt(2020, 1, 1)
                date_to = dt.now()
            else:
                # 增量同步：优先用上次同步时间，否则用命令行参数
                with get_session() as sess:
                    last_sync = get_last_sync(sess, "finance", "sync_orders")
                if last_sync:
                    date_from = last_sync
                    print(f"增量同步：从 last_sync_at={last_sync.strftime('%Y-%m-%d %H:%M:%S')} 开始")
                elif args.date_from:
                    date_from = dt.strptime(args.date_from, "%Y-%m-%d")
                else:
                    date_from = dt(2020, 1, 1)

                date_to = dt.now()
                if args.date_to:
                    date_to = dt.strptime(args.date_to, "%Y-%m-%d")

            result, sync_at = svc.sync_orders(date_from=date_from, date_to=date_to)
            print(result.summary())
            if sync_at:
                print(f"同步完成时间：{sync_at.strftime('%Y-%m-%d %H:%M:%S')}")
            if result.unlinked_skus:
                print(f"⚠️  未关联 SKU（Product 表无此 SKU）：{result.unlinked_skus}")
            return 0

        if args.cmd == "link-costs":
            from datetime import datetime as dt
            since = None
            if args.since:
                since = dt.strptime(args.since, "%Y-%m-%d")
            result = link_costs(dry_run=args.dry_run, since=since)
            print(result.summary())
            if args.export and result.unlinked_skus:
                from pathlib import Path
                n = export_unlinked_xlsx(Path(args.export), since=since)
                print(f"导出 {n} 条 unlinked 订单到 {args.export}")
            return 0

        if args.cmd == "unlinked-orders":
            from datetime import datetime as dt
            since = dt.strptime(args.since, "%Y-%m-%d") if args.since else None
            orders = list_unlinked_orders(since=since)
            if not orders:
                print("没有 unlinked 订单")
                return 0
            for o in orders:
                print(f"  {o['order_id']}  SKU={o['sku']}  amount={o['amount']} {o['currency']}  date={o['date']}")
            if args.export:
                from pathlib import Path
                n = export_unlinked_xlsx(Path(args.export), since=since)
                print(f"导出 {n} 条到 {args.export}")
            return 0

        if args.cmd == "report":
            import datetime

            from modules.finance.report import daily_report, monthly_report, weekly_report

            period = getattr(args, "period", "daily")
            year = getattr(args, "year", datetime.now().year)
            month = getattr(args, "month", datetime.now().month)

            with get_session() as sess:
                if period == "daily":
                    r = daily_report(sess)
                    rep = TransactionReport(sess)
                    print(rep.summary_text(r["date_from"], r["date_to"]))
                elif period == "weekly":
                    r = weekly_report(sess)
                    rep = TransactionReport(sess)
                    print(rep.summary_text(r["date_from"], r["date_to"]))
                elif period == "monthly":
                    r = monthly_report(sess, year, month)
                    from datetime import datetime as dt2
                    start = dt2(year, month, 1)
                    end = dt2(year + 1 if month == 12 else year, (month % 12) + 1, 1)
                    rep = TransactionReport(sess)
                    print(rep.summary_text(start, end))
            return 0

    parser.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(run())
