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
    p_sync_inv = inv_online_sub.add_parser("sync", help="从 eBay 同步 listing")
    p_sync_inv.add_argument(
        "--dry-run",
        action="store_true",
        help="仅打印预览，不写库",
    )
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

    # ── product 模块 ──────────────────────────────────────────────────────
    product_p = sub.add_parser("product", help="商品主数据模块")
    product_sub = product_p.add_subparsers(dest="cmd", help="子命令")

    p_imp_listings = product_sub.add_parser("import-listings", help="从 Excel listing 表预建 SKU 主数据")
    p_imp_listings.add_argument("--file", action="append", required=True, help="Excel 文件路径（可多次指定）")
    p_imp_listings.add_argument("--no-expand-short-links", dest="no_expand_short_links",
                               action="store_true", help="禁用 amzn.asia 短链展开")

    p_imp_amz = product_sub.add_parser(
        "import-amazon-costs",
        help="从 Amazon 注文履歴 CSV 导入进货成本",
    )
    p_imp_amz.add_argument("--file", required=True, help="Amazon 注文履歴 CSV 路径")
    p_imp_amz.add_argument(
        "--output-dir",
        help="报告输出目录（默认 ~/.ebay-project/imports/）",
    )

    p_sync_vars = product_sub.add_parser(
        "sync-variants-from-ebay",
        help="从 eBay Inventory API 拉 active listing 变体，反向写入 products 子 SKU",
    )
    p_sync_vars.add_argument(
        "--dry-run",
        action="store_true",
        help="打印预览，不写库",
    )

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

    p_backfill = finance_sub.add_parser("backfill-amount-jpy", help="回填 Transaction.amount_jpy")
    p_backfill.add_argument("--apply", action="store_true")
    p_backfill.add_argument("--since", dest="since", help="YYYY-MM-DD")
    p_backfill.add_argument("--batch-size", type=int, default=500)

    p_dashboard = finance_sub.add_parser("dashboard", help="财务总览看板")
    p_dashboard.add_argument(
        "--period",
        choices=["all", "this-month", "this-week", "last-7-days", "last-30-days", "custom"],
        default="this-month",
    )
    p_dashboard.add_argument("--from", dest="date_from", help="YYYY-MM-DD")
    p_dashboard.add_argument("--to", dest="date_to", help="YYYY-MM-DD (半开上界)")

    p_breakdown = finance_sub.add_parser("breakdown", help="财务时间分解报表")
    p_breakdown.add_argument("--group-by", choices=["day", "month"], required=True)
    p_breakdown.add_argument(
        "--period",
        choices=["all", "this-month", "this-week", "last-7-days", "last-30-days", "custom"],
        default="this-month",
    )
    p_breakdown.add_argument("--from", dest="date_from", help="YYYY-MM-DD")
    p_breakdown.add_argument("--to", dest="date_to", help="YYYY-MM-DD (半开上界)")

    p_imp_ship = finance_sub.add_parser("import-shipping", help="导入 cpass 运费明细 xlsx")
    p_imp_ship.add_argument("--file", required=True, help="cpass运单费用明细.xlsx 路径")
    p_imp_ship.add_argument("--dry-run", action="store_true", default=False, help="模拟运行,不写 DB")

    currency_p = sub.add_parser("currency", help="汇率模块")
    currency_sub = currency_p.add_subparsers(dest="currency_cmd", help="子命令")
    p_currency_import = currency_sub.add_parser("import-csv", help="导入汇率 CSV")
    p_currency_import.add_argument("csv_path")
    p_currency_import.add_argument("--dry-run", action="store_true", default=False)

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

    if args.module == "currency":
        from core.database.connection import get_session
        from core.utils.currency import import_rates_from_csv

        if args.currency_cmd == "import-csv":
            with get_session() as sess:
                result = import_rates_from_csv(sess, args.csv_path, dry_run=args.dry_run)
            print(result)
            return 0

    if args.module == "finance":
        from modules.finance.cost_linker import export_unlinked_xlsx, link_costs, list_unlinked_orders
        from modules.finance.order_sync_service import OrderSyncService

        if args.cmd == "sync-orders":
            from datetime import datetime
            date_from = None
            date_to = None
            if not args.full:
                if args.date_from:
                    date_from = datetime.strptime(args.date_from, "%Y-%m-%d")
                if args.date_to:
                    date_to = datetime.strptime(args.date_to, "%Y-%m-%d")

            svc = OrderSyncService()
            result = svc.sync_orders(
                date_from=date_from or datetime(2020, 1, 1),
                date_to=date_to or datetime.now(),
            )
            print(result.summary())
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

        if args.cmd == "backfill-amount-jpy":
            from datetime import date as date_type

            from core.database.connection import get_session
            from scripts.backfill_amount_jpy import backfill_transactions

            since = date_type.fromisoformat(args.since) if args.since else None
            with get_session() as sess:
                result = backfill_transactions(
                    sess,
                    dry_run=not args.apply,
                    since=since,
                    batch_size=args.batch_size,
                )
            print(result)
            return 0

        if args.cmd == "dashboard":
            from datetime import datetime

            from core.database.connection import get_session
            from modules.finance.dashboard import DashboardService, DateRange, format_dashboard

            if args.period == "custom" and (not args.date_from or not args.date_to):
                parser.error("finance dashboard --period custom requires --from and --to")

            if args.period == "all":
                date_range = DateRange()
            elif args.period == "this-month":
                date_range = DashboardService.this_month()
            elif args.period == "this-week":
                date_range = DashboardService.this_week()
            elif args.period == "last-7-days":
                date_range = DashboardService.last_n_days(7)
            elif args.period == "last-30-days":
                date_range = DashboardService.last_n_days(30)
            else:
                date_range = DateRange(
                    start=datetime.strptime(args.date_from, "%Y-%m-%d"),
                    end=datetime.strptime(args.date_to, "%Y-%m-%d"),
                )

            with get_session() as sess:
                dashboard = DashboardService(sess).compute(date_range=date_range)
            print(format_dashboard(dashboard))
            return 0

        if args.cmd == "breakdown":
            from datetime import datetime

            from core.database.connection import get_session
            from modules.finance.breakdown import BreakdownService, format_breakdown, resolve_all_range
            from modules.finance.dashboard import DashboardService, DateRange

            if args.period == "custom" and (not args.date_from or not args.date_to):
                parser.error("finance breakdown --period custom requires --from and --to")

            with get_session() as sess:
                if args.period == "all":
                    date_range = resolve_all_range(sess)
                    if date_range.start is None or date_range.end is None:
                        from modules.finance.breakdown import BreakdownResult

                        print(format_breakdown(BreakdownResult(group_by=args.group_by, date_range=date_range, rows=[])))
                        return 0
                elif args.period == "this-month":
                    date_range = DashboardService.this_month()
                elif args.period == "this-week":
                    date_range = DashboardService.this_week()
                elif args.period == "last-7-days":
                    date_range = DashboardService.last_n_days(7)
                elif args.period == "last-30-days":
                    date_range = DashboardService.last_n_days(30)
                else:
                    date_range = DateRange(
                        start=datetime.strptime(args.date_from, "%Y-%m-%d"),
                        end=datetime.strptime(args.date_to, "%Y-%m-%d"),
                    )
                result = BreakdownService(sess).compute(group_by=args.group_by, date_range=date_range)
            print(format_breakdown(result))
            return 0

        if args.cmd == "import-shipping":
            from modules.finance.cpass_importer import import_cpass_shipping

            r = import_cpass_shipping(args.file, dry_run=args.dry_run)
            print(f"total: {r.total_rows}")
            print(f"matched: {r.matched}")
            print(f"unmatched (no tracking): {r.unmatched_no_tracking}")
            print(f"unmatched (cancelled): {r.unmatched_cancelled}")
            print(f"written: {r.written}{'(dry_run)' if args.dry_run else ''}")
            print(f"skipped (Payable=0): {r.skipped_zero}")
            if r.errors:
                print(f"errors ({len(r.errors)}):")
                for e in r.errors:
                    print(f"  - {e}")
            return 0

    if args.module == "product":
        from pathlib import Path

        if args.cmd == "import-listings":
            from modules.listing.listing_importer import ListingImporter
            importer = ListingImporter(expand_short_links=not args.no_expand_short_links)
            paths = [Path(p) for p in args.file]
            result = importer.import_files(paths)
            print(result.summary())
            return 0

        if args.cmd == "import-amazon-costs":
            from modules.finance.amazon_cost_importer import AmazonCostImporter
            importer = AmazonCostImporter(
                output_dir=Path(args.output_dir) if args.output_dir else None,
            )
            result = importer.import_csv(Path(args.file))
            print(result.summary())
            print("\n报告输出:")
            print(f"  {result.summary_txt}")
            print(f"  {result.ambiguous_csv}")
            print(f"  {result.unmapped_csv}")
            print(f"  {result.non_amazon_csv}")
            return 0

        if args.cmd == "sync-variants-from-ebay":
            from modules.listing.variant_sku_syncer import VariantSkuSyncer
            syncer = VariantSkuSyncer()
            result = syncer.sync_from_ebay_listings(dry_run=bool(args.dry_run))
            print(result.summary())
            if result.skipped:
                print("\n跳过详情（写入 variant_sync_skipped.csv）:")
                for s in result.skipped[:10]:
                    print(f"  {s['sku']}  原因={s['reason']}")
            return 0

        parser.print_help()
        return 1

    parser.print_help()


if __name__ == "__main__":
    sys.exit(run())
