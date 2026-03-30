"""
eBay Tax System — CLI 入口
用法：python main.py <command> [options]
"""
import click
from rich.console import Console
from rich.table import Table

console = Console()


@click.group()
def cli():
    """eBay 店铺税务报表自动化系统"""
    pass


@click.command()
def init():
    """初始化数据库"""
    from db.db import init_db
    init_db()
    console.print("[green]✓[/green] 数据库初始化完成")


@click.command()
@click.option("--all", "all_sources", is_flag=True, help="导入所有数据源")
@click.option("--source", type=str, help="指定数据源（ebay / cpass / amazon_jp / hobonichi / bandai / receipts / japanpost）")
@click.option("--file", type=click.Path(exists=True), help="指定输入文件（CSV/XLSX）")
@click.option("--dir", "directory", type=click.Path(exists=True), help="指定输入目录")
@click.option("--from", "date_from", type=str, default=None, help="抓取起始日期 YYYY-MM-DD（hobonichi/bandai 用）")
@click.option("--to", "date_to", type=str, default=None, help="抓取结束日期 YYYY-MM-DD（hobonichi/bandai 用）")
@click.option("--relogin", is_flag=True, help="强制重新登录（清除已保存的 session）")
def ingest(all_sources, source, file, directory, date_from, date_to, relogin):
    """导入数据（CSV/XLSX 文件或网页抓取）"""
    console.print("[bold]开始导入数据...[/bold]")

    if all_sources:
        console.print("[yellow]⚠[/yellow] --all 选项待实现，请先使用 --source 指定数据源")
        return

    if not source and not file:
        console.print("[red]✗[/red] 请指定 --source 或 --file 参数")
        return

    if source == "ebay" or (file and "ebay" in file.lower()):
        from ingest.ebay_orders import ingest_ebay_orders
        if file:
            count = ingest_ebay_orders(file)
            console.print(f"[green]✓[/green] 导入 {count} 条 eBay 订单")
        else:
            console.print("[red]✗[/red] 请指定 --file 参数提供 eBay CSV 文件路径")

    elif source == "cpass" or (file and "cpass" in file.lower()):
        from ingest.cpass import ingest_cpass
        if file:
            count = ingest_cpass(file)
            console.print(f"[green]✓[/green] 导入 {count} 条 CPass 快递记录")
        else:
            console.print("[red]✗[/red] 请指定 --file 参数提供 CPass 文件路径")

    elif source == "amazon_jp" or (file and "amazon" in file.lower()):
        from ingest.amazon_jp import ingest_amazon_jp
        if file:
            count = ingest_amazon_jp(file)
            console.print(f"[green]✓[/green] 导入 {count} 条日本亚马逊采购记录")
        else:
            console.print("[red]✗[/red] 请指定 --file 参数提供亚马逊 CSV 文件路径")

    elif source == "hobonichi":
        from ingest.hobonichi import ingest_hobonichi
        console.print("[bold cyan]ほぼ日ストア[/bold cyan] 订单抓取...")
        if relogin:
            console.print("[yellow]⟳[/yellow] 清除已保存的 session，将重新登录")
        count = ingest_hobonichi(date_from=date_from, date_to=date_to, force_relogin=relogin)
        console.print(f"[green]✓[/green] 导入 {count} 条 ほぼ日ストア 采购记录")

    elif source == "bandai":
        from ingest.bandai import ingest_bandai
        console.print("[bold cyan]Premium Bandai[/bold cyan] 订单抓取...")
        if relogin:
            console.print("[yellow]⟳[/yellow] 清除已保存的 session，将重新登录")
        count = ingest_bandai(date_from=date_from, date_to=date_to, force_relogin=relogin)
        console.print(f"[green]✓[/green] 导入 {count} 条 Premium Bandai 采购记录")

    elif source in ["receipts", "japanpost"]:
        console.print(f"[yellow]⚠[/yellow] 数据源 '{source}' 待实现")

    else:
        console.print(f"[red]✗[/red] 未知的数据源：{source}")


@click.command()
def match():
    """运行自动匹配（采购 ↔ 订单 ↔ 快递）+ FIFO 成本分配"""
    console.print("[bold]开始自动匹配...[/bold]")

    # 先匹配订单与快递
    from matcher.order_shipment import match_order_shipment
    shipment_result = match_order_shipment()

    console.print(f"\n[bold]快递匹配结果:[/bold]")
    console.print(f"  新匹配：{shipment_result['matched']}")
    console.print(f"  未匹配：{shipment_result['unmatched']}")
    console.print(f"  已确认：{shipment_result['confirmed']}")

    # 再匹配采购与订单（v2 三层匹配）
    from matcher.purchase_order import match_purchase_order
    purchase_result = match_purchase_order()

    console.print(f"\n[bold]采购匹配结果（v2 三层匹配）:[/bold]")
    console.print(f"  匹配成功：{purchase_result['matched']}")
    console.print(f"  未匹配：{purchase_result['unmatched']}")
    console.print(f"  Layer1 锚点精确：{purchase_result['layer1']}")
    console.print(f"  Layer2 品牌词典：{purchase_result['layer2']}")
    console.print(f"  Layer3 日期窗口：{purchase_result['layer3']}")

    # FIFO 成本分配
    console.print("\n[bold]执行 FIFO 成本分配...[/bold]")
    from matcher.purchase_order import allocate_fifo, update_inventory
    fifo_result = allocate_fifo()
    console.print(f"  已分配：{fifo_result['allocated']}")
    console.print(f"  跳过：{fifo_result['skipped']}")

    # 更新库存表
    console.print("\n[bold]更新库存表...[/bold]")
    update_inventory()
    console.print("  ✓ 库存表已更新")

    console.print("\n[green]✓[/green] 匹配完成")


@click.command()
@click.option("--type", "review_type", type=click.Choice(["purchase", "shipment", "all"]),
              default="all", show_default=True, help="审核类型")
@click.option("--min-confidence", type=float, default=0.0, help="最低置信度过滤")
@click.option("--max-confidence", type=float, default=1.0, help="最高置信度过滤")
def review(review_type, min_confidence, max_confidence):
    """手动审核未匹配或低置信度记录"""
    console.print(f"[bold]加载未匹配记录（类型：{review_type}）...[/bold]")
    from matcher.manual_review import ManualReviewer
    reviewer = ManualReviewer(review_type, min_confidence, max_confidence)
    result = reviewer.run()
    console.print(f"\n[green]✓[/green] 审核完成：确认 {result['confirmed']} 条，跳过 {result['skipped']} 条，无匹配 {result['no_match']} 条")
    console.print("\n运行 `python main.py status` 查看最新匹配统计。")


@click.command()
@click.option("--year", type=int, required=True, help="报税年份，例如 2025")
@click.option("--month", type=int, default=None, help="月份 1-12；不填则生成全年")
@click.option("--output", type=click.Path(), default="data/outputs", help="输出目录")
@click.option("--skip-screenshots", is_flag=True, help="跳过截图步骤（速度更快）")
def generate(year, month, output, skip_screenshots):
    """生成报表和凭证文件夹"""
    if month is not None:
        console.print(f"[bold]生成 {year}年{month:02d}月 报表...[/bold]")
        report_label = f"{year}-{month:02d}"
    else:
        console.print(f"[bold]生成 {year} 年报表...[/bold]")
        report_label = str(year)

    import os
    from pathlib import Path

    # 确保输出目录存在
    output_path = Path(output)
    output_path.mkdir(parents=True, exist_ok=True)

    # 生成 Excel 报表
    from generator.spreadsheet import generate_report
    excel_path = output_path / f"tax_report_{report_label}.xlsx"
    generate_report(year, str(excel_path), month=month)
    console.print(f"[green]✓[/green] Excel 报表：{excel_path}")

    # 生成订单文件夹
    from generator.folder_builder import build_order_folders
    folder_count = build_order_folders(year, str(output_path), month=month)
    console.print(f"[green]✓[/green] 生成 {folder_count} 个订单文件夹")

    console.print(f"\n[green]✓[/green] 生成完成！输出路径：{output_path}")


@click.command()
def status():
    """查看当前匹配统计"""
    from db.db import fetch_all, count

    # 总 eBay 订单数
    total_orders = count("ebay_orders")

    # 快递统计
    total_shipments = count("shipments")
    matched_shipments = count("shipments", "ebay_order_id IS NOT NULL")

    # 采购统计
    total_purchases = count("purchases")
    matched_purchases = fetch_all("""
        SELECT COUNT(DISTINCT purchase_id) as cnt FROM purchase_order_links
    """)[0]['cnt']

    # 未匹配记录数
    unmatched_shipments = total_shipments - matched_shipments
    unmatched_purchases = total_purchases - matched_purchases

    # 创建表格
    table = Table(title="系统状态", show_header=True, header_style="bold magenta")
    table.add_column("项目", style="cyan")
    table.add_column("数量", style="green")

    table.add_row("eBay 订单总数", str(total_orders))
    table.add_row("快递记录", f"{matched_shipments} / {total_shipments}")
    table.add_row("采购记录", f"{matched_purchases} / {total_purchases}")
    table.add_row("未匹配快递", str(unmatched_shipments))
    table.add_row("未匹配采购", str(unmatched_purchases))

    console.print(table)


@click.command()
def migrate():
    """执行数据库迁移（v2: 添加 FIFO 字段和库存表）"""
    from db.db import fetch_one
    
    # 检查是否已迁移
    existing = fetch_one("""
        SELECT name FROM sqlite_master 
        WHERE type='table' AND name='inventory'
    """)
    
    if existing:
        console.print("[yellow]⟳[/yellow] 数据库已是最新版本")
        return
    
    console.print("[bold]开始数据库迁移 v2...[/bold]")
    
    from db.db import execute
    
    # 添加新字段
    console.print("  📝 添加 purchase_order_links 字段...")
    try:
        execute("ALTER TABLE purchase_order_links ADD COLUMN allocated_qty INTEGER DEFAULT NULL")
        console.print("    ✓ allocated_qty")
    except Exception as e:
        if "duplicate" not in str(e).lower():
            raise
    
    try:
        execute("ALTER TABLE purchase_order_links ADD COLUMN allocated_cost_jpy REAL DEFAULT NULL")
        console.print("    ✓ allocated_cost_jpy")
    except Exception as e:
        if "duplicate" not in str(e).lower():
            raise
    
    try:
        execute("ALTER TABLE purchase_order_links ADD COLUMN allocated_tax_jpy REAL DEFAULT NULL")
        console.print("    ✓ allocated_tax_jpy")
    except Exception as e:
        if "duplicate" not in str(e).lower():
            raise
    
    # 创建 inventory 表
    console.print("  📦 创建 inventory 表...")
    execute("""
        CREATE TABLE IF NOT EXISTS inventory (
            id TEXT PRIMARY KEY,
            item_sku TEXT,
            item_name TEXT,
            item_name_en TEXT,
            total_quantity INTEGER,
            sold_quantity INTEGER DEFAULT 0,
            remaining_quantity INTEGER,
            total_cost_jpy REAL,
            total_tax_jpy REAL,
            average_cost_per_unit REAL,
            last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    console.print("    ✓ inventory 表已创建")
    
    # 创建索引
    console.print("  📇 创建索引...")
    execute("CREATE INDEX IF NOT EXISTS idx_inventory_sku ON inventory(item_sku)")
    execute("CREATE INDEX IF NOT EXISTS idx_pol_allocated ON purchase_order_links(allocated_qty)")
    console.print("    ✓ 索引已创建")
    
    console.print("\n[green]✓[/green] 数据库迁移 v2 完成！")


@click.command()
@click.option("--client-id", prompt="eBay App ID (Client ID)", help="eBay 应用 App ID")
@click.option("--client-secret", prompt="eBay Cert ID (Client Secret)", hide_input=True, help="eBay 应用 Cert ID")
@click.option("--ru-name", prompt="eBay RuName (Redirect URL Name)",
              help="在 eBay Developer Console 注册的回调 URL 名称（格式：YourName-App-xxx）")
def auth(client_id, client_secret, ru_name):
    """
    完成 eBay OAuth 授权，获取并保存 access_token

    \b
    前置步骤（只需做一次）：
    1. 访问 https://developer.ebay.com/my/keys
    2. 选择你的 Production 应用
    3. 在 "User Tokens" → "OAuth Redirect URL" 中添加：
           http://localhost:8080/callback
    4. 记下 RuName（如 YourName-YourApp-Production-xxxxxxxx）
    5. 运行此命令，浏览器会自动打开授权页面
    """
    from auth.ebay_oauth import run_oauth_flow
    try:
        token_data = run_oauth_flow(client_id, client_secret, ru_name)
        console.print("[green]✓[/green] eBay OAuth 授权成功！Token 已保存到 config.yaml")
        console.print(f"  access_token 有效期：{token_data.get('expires_in', 7200)} 秒（约 2 小时）")
        console.print("  refresh_token 有效期：约 18 个月（系统会自动刷新）")
    except Exception as e:
        console.print(f"[red]✗[/red] 授权失败：{e}")


@click.command(name="ingest-api")
@click.option("--from", "date_from", type=str, required=True,
              help="开始日期，格式 YYYY-MM-DD，例如 2026-02-01")
@click.option("--to", "date_to", type=str, default=None,
              help="结束日期，格式 YYYY-MM-DD（默认今天）")
@click.option("--no-fees", is_flag=True, help="跳过 Finances API 费用数据（速度更快）")
def ingest_api(date_from, date_to, no_fees):
    """通过 eBay REST API 直接拉取订单数据（无需导出 CSV）"""
    from auth.ebay_oauth import get_ebay_credentials, refresh_access_token

    creds = get_ebay_credentials()
    if not creds:
        console.print("[red]✗[/red] 未找到 eBay API 凭据，请先运行 `python main.py auth`")
        return

    client_id = creds.get("client_id") or creds.get("app_id")
    client_secret = creds.get("client_secret") or creds.get("cert_id")
    access_token = creds.get("access_token")
    refresh_tok = creds.get("refresh_token")

    if not access_token:
        if refresh_tok and client_id and client_secret:
            console.print("[yellow]⟳[/yellow] access_token 不存在，尝试用 refresh_token 刷新...")
            access_token = refresh_access_token(client_id, client_secret, refresh_tok)
        if not access_token:
            console.print("[red]✗[/red] 无法获取有效 token，请重新运行 `python main.py auth`")
            return

    console.print(f"[bold]通过 eBay API 导入订单...[/bold]")
    try:
        from ingest.ebay_api import ingest_ebay_api
        count = ingest_ebay_api(
            access_token=access_token,
            date_from=date_from,
            date_to=date_to,
            fetch_fees=not no_fees,
        )
        console.print(f"[green]✓[/green] 导入 {count} 条 eBay 订单（通过 API）")
    except PermissionError as e:
        console.print(f"[red]✗[/red] {e}")
        console.print("  → 请运行 `python main.py auth` 重新授权")
    except Exception as e:
        console.print(f"[red]✗[/red] API 导入失败：{e}")


cli.add_command(init)
cli.add_command(ingest)
cli.add_command(auth)
cli.add_command(ingest_api)
cli.add_command(match)
cli.add_command(review)
cli.add_command(generate)
cli.add_command(status)
cli.add_command(migrate)


if __name__ == "__main__":
    cli()
