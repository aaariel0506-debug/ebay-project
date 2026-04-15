#!/usr/bin/env python3
"""
eBay Management System — 统一 CLI 入口

Usage:
    python main.py listing create --file products.csv
    python main.py listing list
    python main.py listing template list
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

    # listing 模块 — 所有子命令由 listing_cli 内部处理
    listing_p = sub.add_parser("listing", help="Listing 模块")
    listing_sub = listing_p.add_subparsers(dest="cmd", help="子命令")

    # create
    p_create = listing_sub.add_parser("create", help="创建 listing")
    p_create.add_argument("--file", help="CSV/XLSX 文件路径（批量上新）")
    p_create.add_argument("--sku", help="单品 SKU")
    p_create.add_argument("--template", dest="template_id", help="模板 ID")
    p_create.add_argument("--price", type=float, help="售价")
    p_create.add_argument("--quantity", type=int, default=1)
    p_create.add_argument("--batch-id", dest="batch_id")
    p_create.add_argument("--no-resume", action="store_true")

    # list
    p_list = listing_sub.add_parser("list", help="列出 listing")
    p_list.add_argument("--status")
    p_list.add_argument("--sku")
    p_list.add_argument("--limit", type=int, default=50)
    p_list.add_argument("--offset", type=int, default=0)

    # template subcommands
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

    # import-template
    p_imp = listing_sub.add_parser("import-template", help="生成导入模板")
    p_imp.add_argument("--output", "-o")

    # status
    _ = listing_sub.add_parser("status", help="查看状态")

    args = parser.parse_args()

    if args.module is None:
        parser.print_help()
        return 0

    if args.module == "listing":
        from api.cli.listing_cli import run_listing_cmd
        return run_listing_cmd(sys.argv[2:] if len(sys.argv) > 2 else [])

    parser.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(run())
