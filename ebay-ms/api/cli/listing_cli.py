"""
Listing CLI — python main.py listing <subcommand>

Usage:
    python main.py listing create --file products.csv
    python main.py listing create --sku ITEM001 --template default
    python main.py listing list
    python main.py listing template list
    python main.py listing template create --name "日本手办"
    python main.py listing import-template
    python main.py listing status
"""

from __future__ import annotations

import argparse
import sys

from loguru import logger as log
from modules.listing.importer import ListingImporter
from modules.listing.service import ListingService
from modules.listing.template_service import TemplateService


def add_create_parser(sub: argparse.ArgumentParser) -> None:
    p = sub.add_parser("create", help="创建 listing")
    p.add_argument("--file", help="CSV/XLSX 文件路径（批量上新）")
    p.add_argument("--sku", help="单品 SKU（单独上新）")
    p.add_argument("--template", dest="template_id", help="引用的模板 ID 或名称")
    p.add_argument("--price", type=float, help="售价（单品模式必填）")
    p.add_argument("--quantity", type=int, default=1, help="数量（默认 1）")
    p.add_argument("--batch-id", dest="batch_id", help="批次 ID（用于中断续传）")
    p.add_argument("--no-resume", dest="no_resume", action="store_true", help="不复续传，从头开始")
    p.set_defaults(fn=cmd_create)


def add_list_parser(sub: argparse.ArgumentParser) -> None:
    p = sub.add_parser("list", help="列出所有 listing 记录")
    p.add_argument("--status", help="按状态过滤（如 ACTIVE, ENDED）")
    p.add_argument("--sku", help="按 SKU 过滤")
    p.add_argument("--limit", type=int, default=50, help="返回条数（默认 50）")
    p.add_argument("--offset", type=int, default=0, help="偏移量（分页）")
    p.set_defaults(fn=cmd_list)


def add_template_parser(sub: argparse.ArgumentParser) -> None:
    tp = sub.add_subparsers(dest="template_cmd", help="模板子命令")
    add_template_list_parser(tp)
    add_template_create_parser(tp)
    add_template_get_parser(tp)
    add_template_delete_parser(tp)


def add_template_list_parser(tp) -> None:
    p = tp.add_parser("list", help="列出所有模板")
    p.set_defaults(fn=cmd_template_list)


def add_template_create_parser(tp) -> None:
    p = tp.add_parser("create", help="创建模板")
    p.add_argument("--name", required=True, help="模板名称")
    p.add_argument("--description-template", dest="description_template", help="描述模板（含占位符 {title} 等）")
    p.add_argument("--category-id", dest="category_id", help="Category ID")
    p.add_argument("--condition", default="NEW", help="商品状况（默认 NEW）")
    p.add_argument("--currency", default="USD", help="币种（默认 USD）")
    p.add_argument("--marketplace-id", dest="marketplace_id", default="EBAY_US", help="市场（默认 EBAY_US）")
    p.add_argument("--shipping-policy-id", dest="shipping_policy_id", help="运费政策 ID")
    p.add_argument("--return-policy-id", dest="return_policy_id", help="退货政策 ID")
    p.add_argument("--payment-policy-id", dest="payment_policy_id", help="支付政策 ID")
    p.add_argument("--default", dest="is_default", action="store_true", help="设为默认模板")
    p.set_defaults(fn=cmd_template_create)


def add_template_get_parser(tp) -> None:
    p = tp.add_parser("get", help="查看模板详情")
    p.add_argument("template_id", help="模板 ID")
    p.set_defaults(fn=cmd_template_get)


def add_template_delete_parser(tp) -> None:
    p = tp.add_parser("delete", help="删除模板")
    p.add_argument("template_id", help="模板 ID")
    p.set_defaults(fn=cmd_template_delete)


def add_import_template_parser(sub: argparse.ArgumentParser) -> None:
    p = sub.add_parser("import-template", help="生成空白导入模板 CSV")
    p.add_argument("--output", "-o", help="输出文件路径（默认 stdout）")
    p.set_defaults(fn=cmd_import_template)


def add_status_parser(sub: argparse.ArgumentParser) -> None:
    p = sub.add_parser("status", help="查看当前 listing 同步状态")
    p.set_defaults(fn=cmd_status)


def cmd_create(args: argparse.Namespace) -> int:
    """创建 listing（单品或批量）。"""
    if args.file:
        # 批量模式
        importer = ListingImporter(
            batch_id=args.batch_id,
            resume=not args.no_resume,
        )
        log.info(f"开始批量导入: {args.file}")
        result = importer.import_file(args.file)
        print(result.summary())
        if result.errors:
            print("\n失败详情:")
            for err in result.errors:
                print(f"  Row {err.row} sku={err.sku}: {err.message}")
        return 0 if result.failure_count == 0 else 1

    elif args.sku:
        # 单品模式
        if not args.price:
            print("错误：单品模式需要 --price", file=sys.stderr)
            return 1

        service = ListingService()
        if args.template_id:
            ts = TemplateService()
            # 尝试用名称找模板（先查 list）
            templates = ts.list_templates()
            tpl = None
            for t in templates:
                if t.id == args.template_id or t.name == args.template_id:
                    tpl = t
                    break
            if not tpl:
                print(f"错误：模板未找到 '{args.template_id}'", file=sys.stderr)
                return 1


            class _FakeRow:
                sku = args.sku
                title = args.sku  # will be overridden
                brand = ""

            product = _FakeRow()
            req = ts.apply_template(
                template_id=tpl.id,
                product=product,
                price=args.price,
                quantity=args.quantity,
            )
        else:
            print("错误：非模板模式需要完整 ListingCreateRequest，请用 --file 批量模式", file=sys.stderr)
            return 1

        resp = service.create_single_listing(req)
        if resp.errors:
            for e in resp.errors:
                print(f"错误: {e}", file=sys.stderr)
            return 1
        print(f"创建成功: item_id={resp.listing_id}")
        return 0

    else:
        print("错误：需要 --file 或 --sku", file=sys.stderr)
        return 1


def cmd_list(args: argparse.Namespace) -> int:
    """列出 listing 记录。"""
    service = ListingService()
    listings = service.list_listings(
        status=args.status,
        sku=args.sku,
        limit=args.limit,
        offset=args.offset,
    )
    if not listings:
        print("无 listing 记录")
        return 0
    print(f"{'SKU':<20} {'Item ID':<20} {'Status':<10} {'Price':>10}")
    print("-" * 62)
    for listing_ in listings:
        print(f"{listing_.sku:<20} {listing_.ebay_item_id or '':<20} {listing_.status:<10} {listing_.listing_price or 0:>10}")
    print(f"\n共 {len(listings)} 条")
    return 0


def cmd_template_list(args: argparse.Namespace) -> int:
    """列出所有模板。"""
    ts = TemplateService()
    templates = ts.list_templates()
    if not templates:
        print("无模板")
        return 0
    print(f"{'ID':<38} {'名称':<20} {'Marketplace':<12} {'Default'}")
    print("-" * 75)
    for t in templates:
        print(f"{t.id:<38} {t.name:<20} {t.marketplace_id or 'N/A':<12} {'*' if t.is_default else ''}")
    print(f"\n共 {len(templates)} 个模板")
    return 0


def cmd_template_create(args: argparse.Namespace) -> int:
    """创建模板。"""
    ts = TemplateService()
    try:
        tpl = ts.create_template(
            name=args.name,
            description_template=args.description_template,
            category_id=args.category_id,
            condition=args.condition,
            shipping_policy_id=args.shipping_policy_id,
            return_policy_id=args.return_policy_id,
            payment_policy_id=args.payment_policy_id,
            is_default=args.is_default,
            currency=args.currency,
            marketplace_id=args.marketplace_id,
        )
        print(f"模板创建成功: id={tpl.id}, name={tpl.name}")
        return 0
    except Exception as exc:
        print(f"错误: {exc}", file=sys.stderr)
        return 1


def cmd_template_get(args: argparse.Namespace) -> int:
    """查看模板详情。"""
    ts = TemplateService()
    try:
        tpl = ts.get_template(args.template_id)
        print(f"ID:      {tpl.id}")
        print(f"名称:    {tpl.name}")
        print(f"Marketplace: {tpl.marketplace_id}  Currency: {tpl.currency}")
        print(f"Category: {tpl.category_id}  Condition: {tpl.condition}")
        print(f"Policies: shipping={tpl.shipping_policy_id}, return={tpl.return_policy_id}, payment={tpl.payment_policy_id}")
        print(f"Default:  {'是' if tpl.is_default else '否'}")
        if tpl.description_template:
            print(f"\n描述模板:\n{tpl.description_template[:200]}")
        return 0
    except Exception as exc:
        print(f"错误: {exc}", file=sys.stderr)
        return 1


def cmd_template_delete(args: argparse.Namespace) -> int:
    """删除模板。"""
    ts = TemplateService()
    try:
        ts.delete_template(args.template_id)
        print(f"模板已删除: {args.template_id}")
        return 0
    except Exception as exc:
        print(f"错误: {exc}", file=sys.stderr)
        return 1


def cmd_import_template(args: argparse.Namespace) -> int:
    """生成空白导入模板。"""
    importer = ListingImporter()
    content = importer.generate_template()
    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(content)
        print(f"模板已生成: {args.output}")
    else:
        print(content)
    return 0


def cmd_status(args: argparse.Namespace) -> int:
    """查看 listing 同步状态。"""
    service = ListingService()
    try:
        # 统计各状态数量
        active = service.list_listings(status="ACTIVE", limit=1)
        ended = service.list_listings(status="ENDED", limit=1)
        total = service.list_listings(limit=1)
        print(f"ACTIVE : {len(active)}+")
        print(f"ENDED  : {len(ended)}+")
        print(f"Total  : {len(total)}+")
    except Exception as exc:
        print(f"状态查询失败: {exc}", file=sys.stderr)
        return 1
    return 0


def run_listing_cmd(argv: list[str] | None = None) -> int:
    """主入口 — python main.py listing ..."""
    # 完整解析器（独立运行时使用）
    parser = argparse.ArgumentParser(prog="listing", description="Listing 管理")
    sub = parser.add_subparsers(dest="cmd", help="子命令")

    p_create = sub.add_parser("create", help="创建 listing")
    p_create.add_argument("--file")
    p_create.add_argument("--sku")
    p_create.add_argument("--template", dest="template_id")
    p_create.add_argument("--price", type=float)
    p_create.add_argument("--quantity", type=int, default=1)
    p_create.add_argument("--batch-id", dest="batch_id")
    p_create.add_argument("--no-resume", action="store_true")

    p_list = sub.add_parser("list", help="列出 listing")
    p_list.add_argument("--status")
    p_list.add_argument("--sku")
    p_list.add_argument("--limit", type=int, default=50)
    p_list.add_argument("--offset", type=int, default=0)

    p_tpl = sub.add_parser("template", help="模板管理")
    p_tpl_sub = p_tpl.add_subparsers(dest="template_cmd")
    _ = p_tpl_sub.add_parser("list")
    p_tpl_get = p_tpl_sub.add_parser("get")
    p_tpl_get.add_argument("template_id")
    p_tpl_create = p_tpl_sub.add_parser("create")
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
    p_tpl_del = p_tpl_sub.add_parser("delete")
    p_tpl_del.add_argument("template_id")

    p_imp = sub.add_parser("import-template", help="生成导入模板")
    p_imp.add_argument("--output", "-o")

    _ = sub.add_parser("status", help="查看状态")

    args = parser.parse_args(argv)
    if args.cmd is None:
        parser.print_help()
        return 0

    # 路由
    if args.cmd == "create":
        return cmd_create(args)
    elif args.cmd == "list":
        return cmd_list(args)
    elif args.cmd == "template":
        return _route_template(args)
    elif args.cmd == "import-template":
        return cmd_import_template(args)
    elif args.cmd == "status":
        return cmd_status(args)
    parser.print_help()
    return 0


def _route_template(args) -> int:
    """路由 template 子命令。"""
    sub = getattr(args, "template_cmd", None)
    if sub == "list":
        return cmd_template_list(args)
    elif sub == "get":
        return cmd_template_get(args)
    elif sub == "create":
        return cmd_template_create(args)
    elif sub == "delete":
        return cmd_template_delete(args)
    # template with no subcmd — print help
    print("usage: listing template [list|get|create|delete]")
    return 0
