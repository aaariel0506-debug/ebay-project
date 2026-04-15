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


def run() -> int:
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

    parser.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(run())
