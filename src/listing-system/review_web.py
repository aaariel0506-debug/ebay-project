#!/usr/bin/env python3
"""
eBay Listing 预审核页面（增强版）
支持所有新增字段：颜色、尺寸、材质、型号、产地、数量折扣、处理时间、配送地区等

用法：python3 review_web.py --port 8080
"""

import os
import json
import argparse
from pathlib import Path
from flask import Flask, render_template, request, redirect, flash, session
from ebay_client import EbayClient
from publish_guard import check_publish_permission

# 设置环境变量强制预审核模式
os.environ['EBAY_FORCE_REVIEW'] = 'true'

# 测试模式：禁止直接发布到 eBay（仅保存草稿）
TEST_MODE = os.environ.get('EBAY_TEST_MODE', 'true').lower() in ('true', '1', 'yes')
if TEST_MODE:
    print("⚠️  测试模式已启用：禁止直接发布到 eBay，仅保存草稿")

app = Flask(__name__)
app.secret_key = os.urandom(24)

TEMPLATE_DIR = Path(__file__).parent / 'templates'
TEMPLATE_DIR.mkdir(exist_ok=True)

HTML = '''<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>eBay Listing 预审核</title>
    <style>
        body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; background: #f5f5f5; padding: 20px; }
        .container { max-width: 1200px; margin: 0 auto; }
        h1 { color: #333; margin-bottom: 10px; }
        .subtitle { color: #666; margin-bottom: 20px; }
        .alert { padding: 12px; border-radius: 6px; margin-bottom: 20px; }
        .alert-success { background: #d1fae5; color: #065f46; }
        .alert-error { background: #fee2e2; color: #991b1b; }
        .alert-info { background: #dbeafe; color: #1e40af; }
        .offer { background: white; padding: 24px; margin: 20px 0; border-radius: 12px; box-shadow: 0 2px 8px rgba(0,0,0,0.1); }
        .offer h3 { margin-top: 0; color: #1f2937; }
        .offer-meta { color: #6b7280; font-size: 14px; margin-bottom: 20px; }
        label { display: block; margin: 12px 0 6px; font-weight: 600; color: #374151; }
        .help-text { font-size: 12px; color: #6b7280; margin-top: 4px; }
        input, textarea, select { width: 100%; padding: 10px; border: 1px solid #d1d5db; border-radius: 6px; font-size: 14px; box-sizing: border-box; }
        textarea { min-height: 120px; font-family: monospace; font-size: 13px; }
        .form-row { display: grid; grid-template-columns: repeat(auto-fit, minmax(250px, 1fr)); gap: 16px; margin-bottom: 12px; }
        .form-group { margin-bottom: 12px; }
        .section { background: #f9fafb; padding: 16px; border-radius: 8px; margin: 20px 0; }
        .section-title { font-weight: 600; color: #1f2937; margin-bottom: 12px; font-size: 16px; border-bottom: 2px solid #e5e7eb; padding-bottom: 8px; }
        .actions { margin-top: 24px; display: flex; gap: 12px; flex-wrap: wrap; }
        button { padding: 12px 24px; border: none; border-radius: 6px; font-weight: 600; cursor: pointer; font-size: 14px; transition: opacity 0.2s; }
        button:hover { opacity: 0.9; }
        .save { background: #3b82f6; color: white; }
        .publish { background: #10b981; color: white; }
        .skip { background: #6b7280; color: white; }
        .result { background: #f9fafb; border-left: 4px solid; padding: 16px; margin-top: 16px; font-family: monospace; font-size: 13px; white-space: pre-wrap; border-radius: 0 6px 6px 0; }
        .result-success { border-color: #10b981; background: #ecfdf5; }
        .result-error { border-color: #ef4444; background: #fef2f2; }
        .image-preview { display: flex; gap: 8px; flex-wrap: wrap; margin-top: 8px; }
        .image-preview img { max-width: 100px; max-height: 100px; border: 1px solid #e5e7eb; border-radius: 4px; }
        .badge { display: inline-block; padding: 2px 8px; border-radius: 12px; font-size: 12px; font-weight: 600; }
        .badge-status { background: #fef3c7; color: #92400e; }
        code { background: #f3f4f6; padding: 2px 6px; border-radius: 4px; font-size: 13px; }
    </style>
</head>
<body>
    <div class="container">
        <h1>🛒 eBay Listing 预审核</h1>
        <p class="subtitle">审核并编辑待发布的 Listing 草稿</p>
        
        {% with messages = get_flashed_messages(with_categories=true) %}
            {% if messages %}
                {% for category, message in messages %}
                    <div class="alert alert-{{ category }}">{{ message }}</div>
                {% endfor %}
            {% endif %}
        {% endwith %}
        
        {% if test_mode %}
        <div class="alert alert-info">
            🔒 <strong>测试模式</strong>：已禁用直接发布功能，所有修改仅保存为草稿。
        </div>
        {% endif %}
        
        {% if not offers %}
        <div class="alert alert-info">
            暂无待审核的 Listing。所有草稿都已处理或没有 UNPUBLISHED 状态的 Offer。
        </div>
        {% endif %}
        
        {% for offer in offers %}
        <div class="offer">
            <h3>{{ offer.title[:80] }}{% if offer.title|length > 80 %}...{% endif %}</h3>
            <p class="offer-meta">
                <span class="badge badge-status">{{ offer.status }}</span>
                Offer ID: <code>{{ offer.offer_id }}</code> | 
                SKU: <code>{{ offer.sku }}</code>
            </p>
            
            <form method="POST" action="/update/{{ offer.offer_id }}">
                <!-- 基本信息 -->
                <div class="section">
                    <div class="section-title">📝 基本信息</div>
                    <div class="form-row">
                        <div class="form-group">
                            <label>SKU</label>
                            <input type="text" name="sku" value="{{ offer.sku }}" readonly style="background: #f3f4f6;">
                        </div>
                        <div class="form-group">
                            <label>标题 (最多 80 字符)</label>
                            <input type="text" name="title" value="{{ offer.title }}" maxlength="80">
                            <div class="help-text">当前：{{ offer.title|length }}/80</div>
                        </div>
                    </div>
                    <div class="form-row">
                        <div class="form-group">
                            <label>副标题 (可选，付费功能)</label>
                            <input type="text" name="subtitle" value="{{ offer.subtitle or '' }}" maxlength="80">
                        </div>
                        <div class="form-group">
                            <label>分类 ID</label>
                            <input type="text" name="category_id" value="{{ offer.category_id }}" readonly style="background: #f3f4f6;">
                        </div>
                    </div>
                </div>
                
                <!-- 价格与库存 -->
                <div class="section">
                    <div class="section-title">💰 价格与库存</div>
                    <div class="form-row">
                        <div class="form-group">
                            <label>价格 ({{ offer.currency }})</label>
                            <input type="number" name="price" value="{{ offer.price }}" step="0.01" min="0">
                        </div>
                        <div class="form-group">
                            <label>库存数量</label>
                            <input type="number" name="quantity" value="{{ offer.quantity }}" min="0">
                        </div>
                    </div>
                    
                    <!-- 数量折扣 -->
                    <div class="form-group">
                        <label>数量折扣 (JSON 格式)</label>
                        <textarea name="quantity_discount" style="min-height: 80px; font-family: monospace;">{{ offer.quantity_discount_json or '[]' }}</textarea>
                        <div class="help-text">
                            示例：<code>[{"quantity": 2, "discount_percent": 10}, {"quantity": 5, "discount_percent": 15}]</code>
                        </div>
                    </div>
                </div>
                
                <!-- 商品属性 -->
                <div class="section">
                    <div class="section-title">🏷️ 商品属性</div>
                    <div class="form-row">
                        <div class="form-group">
                            <label>品牌</label>
                            <input type="text" name="brand" value="{{ offer.brand }}">
                        </div>
                        <div class="form-group">
                            <label>型号</label>
                            <input type="text" name="model" value="{{ offer.model or '' }}">
                        </div>
                    </div>
                    <div class="form-row">
                        <div class="form-group">
                            <label>MPN</label>
                            <input type="text" name="mpn" value="{{ offer.mpn or '' }}">
                        </div>
                        <div class="form-group">
                            <label>UPC</label>
                            <input type="text" name="upc" value="{{ offer.upc or '' }}">
                        </div>
                    </div>
                    <div class="form-row">
                        <div class="form-group">
                            <label>颜色</label>
                            <input type="text" name="color" value="{{ offer.color or '' }}">
                        </div>
                        <div class="form-group">
                            <label>尺寸</label>
                            <input type="text" name="size" value="{{ offer.size or '' }}">
                        </div>
                    </div>
                    <div class="form-row">
                        <div class="form-group">
                            <label>材质</label>
                            <input type="text" name="material" value="{{ offer.material or '' }}">
                        </div>
                        <div class="form-group">
                            <label>产地</label>
                            <input type="text" name="country_of_manufacture" value="{{ offer.country_of_manufacture or '' }}">
                        </div>
                    </div>
                    <div class="form-row">
                        <div class="form-group">
                            <label>类型</label>
                            <input type="text" name="item_type" value="{{ offer.item_type or '' }}">
                        </div>
                        <div class="form-group">
                            <label>系列</label>
                            <input type="text" name="series" value="{{ offer.series or '' }}">
                        </div>
                    </div>
                </div>
                
                <!-- 图片 -->
                <div class="section">
                    <div class="section-title">🖼️ 商品图片</div>
                    <div class="form-group">
                        <label>图片 URL (逗号分隔)</label>
                        <textarea name="image_urls" style="min-height: 80px; font-family: monospace;">{{ offer.image_urls }}</textarea>
                        {% if offer.image_urls %}
                        <div class="image-preview">
                            {% for img_url in offer.image_urls.split(',') %}
                                {% if img_url.strip() %}
                                <img src="{{ img_url.strip() }}" alt="Product Image">
                                {% endif %}
                            {% endfor %}
                        </div>
                        {% endif %}
                    </div>
                </div>
                
                <!-- 描述 -->
                <div class="section">
                    <div class="section-title">📄 商品描述 (HTML)</div>
                    <div class="form-group">
                        <textarea name="description" style="min-height: 200px;">{{ offer.description }}</textarea>
                        <div class="help-text">支持 HTML 标签，如 &lt;b&gt;, &lt;p&gt;, &lt;ul&gt;, &lt;img&gt; 等</div>
                    </div>
                </div>
                
                <!-- 物流设置 -->
                <div class="section">
                    <div class="section-title">📦 物流设置</div>
                    <div class="form-row">
                        <div class="form-group">
                            <label>处理时间 (天)</label>
                            <input type="number" name="handling_time" value="{{ offer.handling_time or 2 }}" min="0">
                        </div>
                        <div class="form-group">
                            <label>促销运费门槛 ({{ offer.currency }})</label>
                            <input type="number" name="promotional_shipping_threshold" value="{{ offer.promotional_shipping_threshold or 50 }}" step="0.01">
                        </div>
                    </div>
                    <div class="form-row">
                        <div class="form-group">
                            <label>配送地区 (逗号分隔)</label>
                            <input type="text" name="ship_to_locations" value="{{ offer.ship_to_locations or 'US,CA,GB,AU' }}">
                            <div class="help-text">示例：<code>US,CA,GB,AU,JP</code></div>
                        </div>
                        <div class="form-group">
                            <label>排除地区 (逗号分隔)</label>
                            <input type="text" name="exclude_ship_to_locations" value="{{ offer.exclude_ship_to_locations or '' }}">
                            <div class="help-text">示例：<code>RU,BY</code></div>
                        </div>
                    </div>
                </div>
                
                <input type="hidden" name="original_sku" value="{{ offer.sku }}">
                <input type="hidden" name="offer_id" value="{{ offer.offer_id }}">
                
                <div class="actions">
                    <button type="submit" name="action" value="save" class="save">💾 保存修改</button>
                    {% if test_mode %}
                    <button type="submit" name="action" value="publish" class="publish" disabled style="background: #9ca3af; cursor: not-allowed;" title="测试模式下禁用">🔒 发布已禁用 (测试模式)</button>
                    {% else %}
                    <button type="submit" name="action" value="publish" class="publish">✅ 保存并发布</button>
                    {% endif %}
                    <button type="submit" name="action" value="skip" class="skip">⏭️ 跳过</button>
                </div>
            </form>
            
            {% if offer.result %}
            <div class="result {{ 'result-success' if offer.result.success else 'result-error' }}">{{ offer.result.message }}</div>
            {% endif %}
        </div>
        {% endfor %}
        
        <div style="margin-top: 40px; padding-top: 20px; border-top: 1px solid #e5e7eb; color: #6b7280; font-size: 14px;">
            <p>💡 提示：修改后点击"保存修改"仅更新草稿，点击"保存并发布"会立即发布到 eBay。</p>
        </div>
    </div>
</body>
</html>'''

(TEMPLATE_DIR / 'review.html').write_text(HTML, encoding='utf-8')


def parse_json_field(value, default=None):
    """解析 JSON 字段"""
    if not value:
        return default
    try:
        return json.loads(value)
    except:
        return default


@app.route('/')
def index():
    client = EbayClient()
    offers = []
    results = session.get('offer_results', {})
    
    # 动态拉取所有 UNPUBLISHED offers
    resp = client.get('/sell/inventory/v1/inventory_item?limit=100')
    if resp.ok and resp.body:
        items = resp.body.get('inventoryItems', [])
        for item in items:
            sku = item.get('sku', '')
            # 查找该 SKU 对应的 offer
            offer_resp = client.get(f'/sell/inventory/v1/offer?sku={sku}')
            if offer_resp.ok and offer_resp.body:
                offer_list = offer_resp.body.get('offers', [])
                for offer in offer_list:
                    if offer.get('status') == 'UNPUBLISHED':
                        offer_id = offer.get('offerId', '')
                        product = item.get('product', {})
                        aspects = product.get('aspects', {})
                        
                        # 提取数量折扣 JSON
                        qty_discount = offer.get('pricingSummary', {}).get('quantityDiscountPricing', {})
                        qty_discount_json = '[]'
                        if qty_discount:
                            tiers = qty_discount.get('quantityDiscountTiers', [])
                            qty_discount_json = json.dumps([
                                {
                                    'quantity': t.get('minimumQuantity', 0),
                                    'discount_percent': round((1 - float(t.get('price', {}).get('value', 0)) / float(offer.get('pricingSummary', {}).get('price', {}).get('value', 1))) * 100)
                                }
                                for t in tiers
                            ], indent=2)
                        
                        # 提取物流设置
                        fulfillment = offer.get('fulfillmentStartEndDate', {})
                        handling_time = fulfillment.get('handlingTime', {}).get('value', 2)
                        ship_to = ','.join([loc.get('regionCode', '') for loc in fulfillment.get('shipToLocations', [])])
                        exclude_ship_to = ','.join([loc.get('regionCode', '') for loc in fulfillment.get('excludeShipToLocations', [])])
                        
                        # 提取促销运费
                        promo_shipping = offer.get('promotionalShippingPolicies', [])
                        promo_threshold = ''
                        if promo_shipping:
                            promo_threshold = promo_shipping[0].get('minimumOrderAmount', {}).get('value', '50')
                        
                        offers.append({
                            'offer_id': offer_id,
                            'sku': sku,
                            'title': product.get('title', ''),
                            'subtitle': offer.get('title', ''),  # 副标题在 offer 层级
                            'description': product.get('description', '') or offer.get('listingDescription', ''),
                            'price': offer.get('pricingSummary', {}).get('price', {}).get('value', '0'),
                            'currency': offer.get('pricingSummary', {}).get('price', {}).get('currency', 'USD'),
                            'quantity': item.get('availability', {}).get('shipToLocationAvailability', {}).get('quantity', 0),
                            'category_id': offer.get('categoryId', ''),
                            'brand': aspects.get('Brand', [''])[0] if aspects.get('Brand') else '',
                            'mpn': aspects.get('MPN', [''])[0] if aspects.get('MPN') else '',
                            'model': aspects.get('Model', [''])[0] if aspects.get('Model') else '',
                            'upc': product.get('upc', [''])[0] if product.get('upc') else '',
                            'color': aspects.get('Color', [''])[0] if aspects.get('Color') else '',
                            'size': aspects.get('Size', [''])[0] if aspects.get('Size') else '',
                            'material': aspects.get('Material', [''])[0] if aspects.get('Material') else '',
                            'country_of_manufacture': aspects.get('Country/Region of Manufacture', [''])[0] if aspects.get('Country/Region of Manufacture') else '',
                            'item_type': aspects.get('Type', [''])[0] if aspects.get('Type') else '',
                            'series': aspects.get('Series', [''])[0] if aspects.get('Series') else '',
                            'image_urls': ','.join(product.get('imageUrls', [])),
                            'quantity_discount_json': qty_discount_json,
                            'handling_time': handling_time,
                            'ship_to_locations': ship_to,
                            'exclude_ship_to_locations': exclude_ship_to,
                            'promotional_shipping_threshold': promo_threshold,
                            'status': offer.get('status'),
                            'result': results.get(offer_id)
                        })
    
    # 按 SKU 排序
    offers.sort(key=lambda x: x['sku'])
    
    return render_template('review.html', offers=offers, test_mode=TEST_MODE)


@app.route('/update/<offer_id>', methods=['POST'])
def update(offer_id):
    client = EbayClient()
    action = request.form.get('action')
    original_sku = request.form.get('original_sku')
    result = {'success': False, 'message': ''}
    
    if action == 'skip':
        result = {'success': True, 'message': '已跳过'}
        flash('已跳过', 'info')
    elif action == 'publish' and TEST_MODE:
        result = {'success': False, 'message': '测试模式下禁止发布，仅保存草稿'}
        flash('⚠️  测试模式下禁止发布，已保存草稿', 'info')
        action = 'save'  # 降级为保存操作
    else:
        # 获取现有数据
        resp = client.get(f'/sell/inventory/v1/inventory_item/{original_sku}')
        if not resp.ok:
            result = {'success': False, 'message': f'获取失败：{resp.error}'}
            flash('获取失败', 'error')
        else:
            existing = resp.body
            product = existing.get('product', {})
            
            # 构建更新后的 product
            body = {
                'product': {
                    'title': request.form.get('title', product.get('title', '')),
                    'description': request.form.get('description', product.get('description', '')),
                },
                'condition': existing.get('condition', 'NEW'),
                'availability': {
                    'shipToLocationAvailability': {
                        'quantity': int(request.form.get('quantity', 1))
                    }
                },
            }
            
            # 图片
            image_urls = request.form.get('image_urls', '')
            if image_urls:
                body['product']['imageUrls'] = [u.strip() for u in image_urls.split(',') if u.strip()]
            elif product.get('imageUrls'):
                body['product']['imageUrls'] = product['imageUrls']
            
            # Aspects - 所有属性字段
            aspects = product.get('aspects', {}).copy()
            
            aspect_fields = [
                'brand', 'model', 'mpn', 'color', 'size', 'material',
                'country_of_manufacture', 'item_type', 'series'
            ]
            
            for field in aspect_fields:
                value = request.form.get(field, '').strip()
                if value:
                    # 特殊处理产地字段名
                    api_field = field if field != 'country_of_manufacture' else 'Country/Region of Manufacture'
                    aspects[api_field] = [value]
                elif field in aspects:
                    del aspects[field]
            
            if aspects:
                body['product']['aspects'] = aspects
            
            # UPC
            upc = request.form.get('upc', '').strip()
            if upc:
                body['product']['upc'] = [upc]
            elif product.get('upc'):
                body['product']['upc'] = product['upc']
            
            # 包装信息
            if existing.get('packageWeightAndSize'):
                body['packageWeightAndSize'] = existing['packageWeightAndSize']
            
            # 更新 Inventory Item
            update_resp = client.put(f'/sell/inventory/v1/inventory_item/{original_sku}', data=body)
            if not update_resp.ok:
                result = {'success': False, 'message': f'保存失败：{update_resp.error}'}
                flash('保存失败', 'error')
            else:
                # 如果需要发布
                if action == 'publish':
                    can_pub, reason = check_publish_permission('review_web', offer_id)
                    if not can_pub:
                        result = {'success': False, 'message': f'发布被拒绝：{reason}'}
                        flash('发布被拒绝', 'error')
                    else:
                        pub_resp = client.post(f'/sell/inventory/v1/offer/{offer_id}/publish')
                        if pub_resp.ok:
                            listing_id = pub_resp.body.get('listingId') if pub_resp.body else None
                            env = client.config.get('environment', 'sandbox')
                            web_base = 'https://www.sandbox.ebay.com' if env == 'sandbox' else 'https://www.ebay.com'
                            result = {'success': True, 'message': f'发布成功!\nListing ID: {listing_id}\n{web_base}/itm/{listing_id}'}
                            flash('发布成功', 'success')
                        else:
                            result = {'success': False, 'message': f'保存成功，发布失败：{pub_resp.error}'}
                            flash('发布失败', 'error')
                else:
                    result = {'success': True, 'message': '保存成功'}
                    flash('保存成功', 'success')
    
    if 'offer_results' not in session:
        session['offer_results'] = {}
    session['offer_results'][offer_id] = result
    session.modified = True
    return redirect('/')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--port', type=int, default=8080)
    args = parser.parse_args()
    print(f"启动预审核页面：http://127.0.0.1:{args.port}")
    print("提示：修改后点击\"保存修改\"仅更新草稿，点击\"保存并发布\"会立即发布到 eBay。")
    app.run(host='127.0.0.1', port=args.port, debug=True)
