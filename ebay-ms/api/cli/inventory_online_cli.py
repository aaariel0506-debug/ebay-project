"""api/cli/inventory_online_cli.py

Day 16: inventory online 子命令 — price-check / price-history / margin-check
"""

import sys
from pathlib import Path


def run_inventory_online_cmd(argv: list[str]) -> int:
    import argparse

    parser = argparse.ArgumentParser(prog="main.py inventory online")
    sub = parser.add_subparsers(dest="cmd", help="子命令")

    # price-check：检查进货价变化
    p_price_check = sub.add_parser("price-check", help="检查进货价变化")
    p_price_check.add_argument("--sku", help="单个 SKU")
    p_price_check.add_argument(
        "--file",
        type=Path,
        help="CSV 文件路径（批量），格式：sku,new_price,supplier（可选）,note（可选）",
    )
    p_price_check.add_argument(
        "--threshold",
        type=float,
        default=0.10,
        help="价格变化阈值（默认 10%%）",
    )
    p_price_check.add_argument(
        "--min-margin",
        type=float,
        default=0.15,
        help="最低利润率阈值（默认 15%%）",
    )

    # price-history：查看价格历史
    p_history = sub.add_parser("price-history", help="查看 SKU 进货价历史")
    p_history.add_argument("sku", help="SKU")

    # margin-check：查看利润率不达标的商品
    p_margin = sub.add_parser("margin-check", help="检查利润率低于阈值的商品")
    p_margin.add_argument(
        "--threshold",
        type=float,
        default=0.15,
        help="利润率阈值（默认 15%%）",
    )

    # restock-advice：补货建议
    p_restock = sub.add_parser("restock-advice", help="生成补货建议")
    p_restock.add_argument(
        "--days",
        type=int,
        default=30,
        dest="lookback_days",
        help="分析近 N 天销售数据（默认 30 天）",
    )
    p_restock.add_argument(
        "--urgent-days",
        type=int,
        default=7,
        dest="urgent_days",
        help="紧急阈值天数（默认 7 天）",
    )
    p_restock.add_argument(
        "--soon-days",
        type=int,
        default=14,
        dest="soon_days",
        help="近期阈值天数（默认 14 天）",
    )

    # adjust：eBay 库存调整
    p_adjust = sub.add_parser("adjust", help="调整 eBay 库存数量")
    p_adjust.add_argument("--sku", help="单个 SKU")
    p_adjust.add_argument("--quantity", type=int, help="新的库存数量")
    p_adjust.add_argument(
        "--file",
        type=Path,
        help="CSV 文件路径（批量），格式：sku,new_quantity",
    )
    p_adjust.add_argument(
        "--dry-run",
        action="store_true",
        dest="dry_run",
        help="仅打印，不实际调整",
    )

    args = parser.parse_args(argv)

    if args.cmd == "price-check":
        return _cmd_price_check(args)
    elif args.cmd == "price-history":
        return _cmd_price_history(args)
    elif args.cmd == "margin-check":
        return _cmd_margin_check(args)
    elif args.cmd == "restock-advice":
        return _cmd_restock_advice(args)
    elif args.cmd == "adjust":
        return _cmd_adjust(args)
    else:
        parser.print_help()
        return 0


def _cmd_price_check(args) -> int:
    from modules.inventory_online.price_monitor import PriceMonitor

    pm = PriceMonitor(
        price_change_threshold=args.threshold,
        min_profit_margin=args.min_margin,
    )

    if args.sku:
        # 单个 SKU
        from decimal import Decimal
        try:
            new_price_str = input(f"请输入 {args.sku} 的新进货价（JPY）: ").strip()
            alert = pm.update_cost_price(
                sku=args.sku,
                new_price=Decimal(new_price_str),
            )
            _print_alert(alert)
        except Exception as e:
            print(f"❌ 错误: {e}", file=sys.stderr)
            return 1
        return 0

    if args.file:
        result = pm.batch_update_from_csv(args.file)
        print(f"\n{'='*50}")
        print("批量价格更新结果")
        print(f"{'='*50}")
        print(f"总计: {result.total} | 成功: {result.success} | 失败: {result.failed}")

        if result.alerts:
            triggered = [a for a in result.alerts if a.triggered]
            if triggered:
                print(f"\n⚠️  触发预警 ({len(triggered)} 件):")
                for a in triggered:
                    _print_alert(a)
            else:
                print("\n✅ 所有价格变化在阈值内，无预警")

        if result.errors:
            print(f"\n❌ 失败 ({len(result.errors)} 件):")
            for err in result.errors:
                print(f"  - {err['sku']}: {err['error']}")

        return 0

    # 无参数：显示帮助
    print("请提供 --sku 或 --file 参数", file=sys.stderr)
    return 1


def _cmd_price_history(args) -> int:
    from modules.inventory_online.price_monitor import PriceMonitor

    pm = PriceMonitor()
    history = pm.get_price_history(args.sku)

    if not history:
        print(f"无价格历史记录: {args.sku}")
        return 0

    print(f"\n价格历史: {args.sku}")
    print(f"{'日期':<12} {'价格':>10} {'货币':<5} {'供应商':<15} {'备注'}")
    print("-" * 65)
    for rec in history:
        print(
            f"{str(rec.recorded_at):<12} "
            f"{float(rec.price):>10.2f} "
            f"{rec.currency:<5} "
            f"{(rec.supplier or ''):<15} "
            f"{rec.note or ''}"
        )
    return 0


def _cmd_margin_check(args) -> int:
    from core.database.connection import get_session
    from core.models import EbayListing, Product

    with get_session() as sess:
        listings = sess.query(EbayListing, Product).join(
            Product, EbayListing.sku == Product.sku
        ).filter(
            EbayListing.listing_price.isnot(None),
            EbayListing.quantity_available > 0,
        ).all()

    min_margin = getattr(args, 'threshold', 0.15)
    print(f"\n利润率低于 {min_margin:.1%} 的商品:")
    print(f"{'SKU':<20} {'售价':>8} {'成本':>8} {'利润率':>8}")
    print("-" * 50)

    low_margin_items = []
    for listing, product in listings:
        listing_price = float(listing.listing_price)
        cost_price = float(product.cost_price)
        if listing_price > 0:
            margin = (listing_price - cost_price) / listing_price
            if margin < min_margin:
                low_margin_items.append((listing.sku, listing_price, cost_price, margin))
                print(
                    f"{listing.sku:<20} "
                    f"${listing_price:>7.2f} "
                    f"¥{cost_price:>7.2f} "
                    f"{margin:>7.1%}"
                )

    if not low_margin_items:
        print("✅ 所有商品利润率达标")
    return 0


def _cmd_restock_advice(args) -> int:
    from modules.inventory_online.restock_advisor import RestockAdvisor

    advisor = RestockAdvisor(
        urgent_days=args.urgent_days,
        soon_days=args.soon_days,
    )
    advisor.print_report(lookback_days=args.lookback_days)
    return 0


def _cmd_adjust(args) -> int:
    from modules.inventory_online.quantity_adjuster import QuantityAdjuster

    adjuster = QuantityAdjuster()

    if args.sku is not None and args.quantity is not None:
        # 单个 SKU 调整
        result = adjuster.adjust_ebay_quantity(args.sku, args.quantity)
        if result.success:
            print(f"✅ {result.sku}: 库存 {result.old_quantity} → {result.new_quantity}")
        else:
            print(f"❌ {result.sku}: {result.error}", file=sys.stderr)
            return 1
        return 0

    if args.file:
        result = adjuster.batch_adjust_from_csv(args.file, dry_run=args.dry_run)
        print(f"\n{'='*50}")
        mode = "[DRY RUN]" if args.dry_run else ""
        print(f"批量库存调整 {mode}")
        print(f"{'='*50}")
        print(f"总计: {result.total} | 成功: {result.success} | 失败: {result.failed}")
        if result.failed > 0:
            for r in result.results:
                if not r.success:
                    print(f"  ❌ {r.sku}: {r.error}")
        return 0

    print("请提供 --sku + --quantity 或 --file 参数", file=sys.stderr)
    return 1


def _print_alert(alert) -> None:
    status = "⚠️  预警" if alert.triggered else "✅ 正常"
    print(f"\n{'='*50}")
    print(f"{status} — {alert.sku} ({alert.title or ''})")
    print(f"{'='*50}")
    print(f"  进货价: ¥{alert.old_price} → ¥{alert.new_price} ({alert.change_rate:+.1%})")
    if alert.old_listing_price:
        print(f"  eBay 售价: ${alert.old_listing_price:.2f}")
    if alert.new_margin is not None:
        print(f"  新利润率: {alert.new_margin:.1%}")
    print(f"  建议: {alert.suggested_action}")
