"""
generator/html_order_page.py — 生成 HTML 订单页面（替代 Playwright 截图）

从数据库读取数据生成两种 HTML 页面：
1. 订单详情页 (Order Detail)
2. 订单收据页 (Order Receipt)
"""
from datetime import datetime
from db.db import fetch_all, fetch_one


def _usd(value) -> str:
    """格式化美元金额"""
    return f"{(value or 0):.2f}"


def _jpy(value) -> str:
    """格式化日元金额"""
    return f"{int(value or 0):,}"


def _conf(value) -> str:
    """格式化置信度"""
    return f"{float(value or 0):.2f}"


def _get_order_data(order_id: str) -> dict | None:
    """获取订单完整数据（含关联的快递和采购信息）"""
    order = fetch_one("SELECT * FROM ebay_orders WHERE order_id = ?", (order_id,))
    if not order:
        return None

    shipments = fetch_all(
        "SELECT * FROM shipments WHERE ebay_order_id = ?", (order_id,)
    )

    links = fetch_all(
        "SELECT * FROM purchase_order_links WHERE ebay_order_id = ?", (order_id,)
    )
    purchases = []
    for link in links:
        purchase = fetch_one(
            "SELECT * FROM purchases WHERE id = ?", (link['purchase_id'],)
        )
        if purchase:
            p = dict(purchase)
            p['match_method'] = link.get('match_method', 'N/A')
            p['confidence'] = link.get('confidence', 0)
            purchases.append(p)

    return {
        'order': dict(order),
        'shipments': [dict(s) for s in shipments],
        'purchases': purchases,
    }


CSS = """
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body { font-family: Arial, sans-serif; font-size: 14px; color: #333; background: #fff; }
    .container { max-width: 900px; margin: 20px auto; padding: 20px; }
    .header { background: #1a1a2e; color: white; padding: 20px; margin-bottom: 20px; }
    .header h1 { font-size: 20px; margin-bottom: 5px; }
    .header .subtitle { font-size: 12px; opacity: 0.8; }
    .section { border: 1px solid #ddd; margin-bottom: 20px; border-radius: 4px; overflow: hidden; }
    .section h2 { background: #f5f5f5; padding: 10px 15px; font-size: 14px;
                  border-bottom: 1px solid #ddd; color: #555; }
    .info-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 0; }
    .info-item { padding: 10px 15px; border-bottom: 1px solid #eee; }
    .info-item:nth-child(odd) { border-right: 1px solid #eee; }
    .label { font-size: 11px; color: #888; text-transform: uppercase; margin-bottom: 3px; }
    .value { font-size: 14px; font-weight: 500; }
    table { width: 100%; border-collapse: collapse; }
    th { background: #f5f5f5; padding: 8px 12px; text-align: left;
         font-size: 12px; color: #666; border-bottom: 1px solid #ddd; }
    td { padding: 8px 12px; border-bottom: 1px solid #eee; font-size: 13px; }
    tr:last-child td { border-bottom: none; }
    .fee-table td:first-child { color: #666; }
    .fee-table td:last-child { text-align: right; font-weight: 500; }
    .total-row td { font-weight: bold; border-top: 2px solid #333; }
    .footer { text-align: center; font-size: 11px; color: #aaa; margin-top: 20px; padding-top: 10px;
              border-top: 1px solid #eee; }
    .badge { display: inline-block; padding: 2px 8px; border-radius: 3px;
             font-size: 11px; background: #e8f5e9; color: #2e7d32; }
    @media print {
        body { font-size: 12px; }
        .container { margin: 0; padding: 10px; }
        .header { background: #333 !important; -webkit-print-color-adjust: exact; }
        .section { break-inside: avoid; }
    }
"""


def generate_order_detail(order_id: str, output_path: str) -> str:
    """生成订单详情页 HTML"""
    data = _get_order_data(order_id)
    if not data:
        raise ValueError(f"Order not found: {order_id}")

    order = data['order']
    shipments = data['shipments']
    purchases = data['purchases']
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    # 预计算快递行
    if shipments:
        shipment_rows = ""
        for s in shipments:
            shipment_rows += (
                "<tr>"
                "<td>" + (s['carrier'] or 'N/A') + "</td>"
                "<td>" + (s['tracking_number'] or 'N/A') + "</td>"
                "<td>" + (s['ship_date'] or 'N/A') + "</td>"
                "<td>$" + _usd(s['shipping_fee_usd']) + "</td>"
                "</tr>"
            )
        shipment_section = (
            "<table>"
            "<tr><th>Carrier</th><th>Tracking Number</th><th>Ship Date</th><th>Shipping Fee (USD)</th></tr>"
            + shipment_rows +
            "</table>"
        )
    else:
        shipment_section = "<p style='padding:15px;color:#888;'>No shipping records found.</p>"

    # 预计算采购行
    if purchases:
        purchase_rows = ""
        for p in purchases:
            purchase_rows += (
                "<tr>"
                "<td>" + (p['platform'] or 'N/A') + "</td>"
                "<td>" + (p['item_name'] or 'N/A') + "</td>"
                "<td>" + str(p['quantity'] or 1) + "</td>"
                "<td>&#165;" + _jpy(p['total_price_jpy']) + "</td>"
                "<td>&#165;" + _jpy(p['tax_jpy']) + "</td>"
                "<td>" + (p['match_method'] or 'N/A') + " (" + _conf(p['confidence']) + ")</td>"
                "</tr>"
            )
        purchase_section = (
            "<table>"
            "<tr><th>Platform</th><th>Item Name</th><th>Qty</th>"
            "<th>Total (JPY)</th><th>Tax (JPY)</th><th>Match</th></tr>"
            + purchase_rows +
            "</table>"
        )
    else:
        purchase_section = "<p style='padding:15px;color:#888;'>No purchase records found.</p>"

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Order Details — {order_id}</title>
<style>{CSS}</style>
</head>
<body>
<div class="container">
  <div class="header">
    <h1>Order Details</h1>
    <div class="subtitle">Order ID: {order_id} &nbsp;|&nbsp; Generated: {now}</div>
  </div>

  <div class="section">
    <h2>Order Information</h2>
    <div class="info-grid">
      <div class="info-item"><div class="label">Order ID</div><div class="value">{order_id}</div></div>
      <div class="info-item"><div class="label">Sale Date</div><div class="value">{order.get('sale_date') or 'N/A'}</div></div>
      <div class="info-item"><div class="label">Buyer</div><div class="value">{order.get('buyer_username') or 'N/A'}</div></div>
      <div class="info-item"><div class="label">Ship To Country</div><div class="value">{order.get('shipping_address_country') or 'N/A'}</div></div>
      <div class="info-item"><div class="label">Status</div><div class="value"><span class="badge">{order.get('order_status') or 'N/A'}</span></div></div>
      <div class="info-item"><div class="label">Item ID</div><div class="value">{order.get('item_id') or 'N/A'}</div></div>
    </div>
  </div>

  <div class="section">
    <h2>Item</h2>
    <div class="info-grid">
      <div class="info-item" style="grid-column:1/-1"><div class="label">Title</div><div class="value">{order.get('item_title') or 'N/A'}</div></div>
      <div class="info-item"><div class="label">Quantity</div><div class="value">{order.get('quantity') or 1}</div></div>
      <div class="info-item"><div class="label">Sale Price</div><div class="value">${_usd(order.get('sale_price_usd'))}</div></div>
    </div>
  </div>

  <div class="section">
    <h2>Fees &amp; Payment</h2>
    <table class="fee-table">
      <tr><td>Sale Price</td><td>${_usd(order.get('sale_price_usd'))}</td></tr>
      <tr><td>Buyer Shipping</td><td>${_usd(order.get('shipping_charged_usd'))}</td></tr>
      <tr><td>eBay Platform Fee</td><td>-${_usd(order.get('ebay_fee_usd'))}</td></tr>
      <tr><td>eBay Ad Fee</td><td>-${_usd(order.get('ebay_ad_fee_usd'))}</td></tr>
      <tr class="total-row"><td>Net Payment</td><td>${_usd(order.get('payment_net_usd'))}</td></tr>
    </table>
  </div>

  <div class="section">
    <h2>Shipping</h2>
    {shipment_section}
  </div>

  <div class="section">
    <h2>Purchase Records</h2>
    {purchase_section}
  </div>

  <div class="footer">Generated by eBay Tax System &nbsp;|&nbsp; {now}</div>
</div>
</body>
</html>"""

    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(html)
    return output_path


def generate_order_receipt(order_id: str, output_path: str) -> str:
    """生成订单收据页 HTML"""
    data = _get_order_data(order_id)
    if not data:
        raise ValueError(f"Order not found: {order_id}")

    order = data['order']
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    sale_price = order.get('sale_price_usd') or 0
    buyer_shipping = order.get('shipping_charged_usd') or 0
    ebay_fee = order.get('ebay_fee_usd') or 0
    ad_fee = order.get('ebay_ad_fee_usd') or 0
    net = order.get('payment_net_usd') or 0

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>Order Receipt — {order_id}</title>
<style>
{CSS}
.receipt-header {{ display: flex; justify-content: space-between; align-items: center;
                   padding: 20px; border-bottom: 2px solid #333; margin-bottom: 20px; }}
.ebay-logo {{ font-size: 28px; font-weight: bold; color: #e53238; }}
.ebay-logo span {{ color: #0064d2; }}
.receipt-title {{ font-size: 22px; font-weight: bold; }}
.order-meta {{ color: #666; font-size: 13px; margin-bottom: 20px; }}
</style>
</head>
<body>
<div class="container">
  <div class="receipt-header">
    <div class="ebay-logo">e<span>b</span>ay</div>
    <div class="receipt-title">Order Receipt</div>
  </div>

  <div class="order-meta">
    <strong>Order ID:</strong> {order_id} &nbsp;&nbsp;
    <strong>Date:</strong> {order.get('sale_date') or 'N/A'} &nbsp;&nbsp;
    <strong>Buyer:</strong> {order.get('buyer_username') or 'N/A'}
  </div>

  <div class="section">
    <h2>Items Purchased</h2>
    <table>
      <tr><th>Item</th><th>Item ID</th><th style="text-align:right">Qty</th><th style="text-align:right">Price</th></tr>
      <tr>
        <td>{order.get('item_title') or 'N/A'}</td>
        <td>{order.get('item_id') or 'N/A'}</td>
        <td style="text-align:right">{order.get('quantity') or 1}</td>
        <td style="text-align:right">${_usd(sale_price)}</td>
      </tr>
    </table>
  </div>

  <div class="section">
    <h2>Order Summary</h2>
    <table class="fee-table">
      <tr><td>Item Subtotal</td><td style="text-align:right">${_usd(sale_price)}</td></tr>
      <tr><td>Shipping &amp; Handling</td><td style="text-align:right">${_usd(buyer_shipping)}</td></tr>
      <tr><td>eBay Final Value Fee</td><td style="text-align:right">-${_usd(ebay_fee)}</td></tr>
      <tr><td>Promoted Listing Fee</td><td style="text-align:right">-${_usd(ad_fee)}</td></tr>
      <tr class="total-row"><td>Total Net Received</td><td style="text-align:right">${_usd(net)}</td></tr>
    </table>
  </div>

  <div class="footer">
    This receipt is generated from eBay order data for tax documentation purposes.<br>
    Generated: {now}
  </div>
</div>
</body>
</html>"""

    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(html)
    return output_path
