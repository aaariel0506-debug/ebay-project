#!/usr/bin/env python3
"""
跨语言智能匹配 - 通过品牌 + 型号 + 尺寸关键词匹配日文采购和英文订单
"""
import sqlite3
import re

DB_PATH = '/Users/arielhe/.openclaw/workspace/ebay-tax-system/data/orders.db'

# 品牌映射（日文 → 英文关键词）
BRAND_MAP = {
    'ユーエム工業': 'Silky',
    'シルキー': 'Silky',
    'Silky': 'Silky',
    '貝印': 'KAI',
    'Kai Corporation': 'KAI',
    'GREEN BELL': 'GREEN BELL',
    '匠の技': 'GREEN BELL',
    'グリーンベル': 'GREEN BELL',
    '無印良品': 'MUJI',
    'MUJI': 'MUJI',
    '三菱鉛筆': 'Uni Jetstream',
    'ジェットストリーム': 'Jetstream',
    'ゼブラ': 'Zebra',
    'コクヨ': 'Kokuyo',
    'タカラトミー': 'Takara Tomy',
    'バンダイ': 'Bandai',
    'タミヤ': 'Tamiya',
    'エンスカイ': 'Ensky',
    'サンリオ': 'Sanrio',
    'ハローキティ': 'Hello Kitty',
    'ほぼ日': 'Hobonichi',
    'パディントン': 'Paddington',
    '北岸由美': 'Yumi Kitagishi',
    '伊藤潤二': 'Junji Ito',
    '富江': 'Tomie',
    'ニューエラ': 'New Era',
    '下村企販': 'Shimomura',
    '下村工業': 'Shimomura',
    'ヴェルダン': 'Verdun',
    'Schick': 'Schick',
    'シック': 'Schick',
    'Gillette': 'Gillette',
    'ジレット': 'Gillette',
    'FEATHER': 'FEATHER',
    'フェザー': 'FEATHER',
    'JVC': 'JVC',
    'ソニー': 'Sony',
    'SONY': 'Sony',
    'ワンピース': 'One Piece',
    'ONE PIECE': 'One Piece',
    'ドラゴンボール': 'Dragon Ball',
    'ポケモン': 'Pokemon',
    'チェンソーマン': 'Chainsaw Man',
    'BLEACH': 'BLEACH',
    '米津玄師': 'Kenshi Yonezu',
    '浜崎あゆみ': 'Ayumi Hamasaki',
    'テイラー・スウィフト': 'Taylor Swift',
    'Radiohead': 'Radiohead',
    'ブルース・スプリングスティーン': 'Bruce Springsteen',
    'ペット・ショップ・ボーイズ': 'Pet Shop Boys',
    'Scorpions': 'Scorpions',
    '高中正義': 'Masayoshi Takanaka',
    'Stray Kids': 'Stray Kids',
    'ILLIT': 'ILLIT',
    'ヒラリー・ダフ': 'Hilary Duff',
    'シルバニア': 'Sylvanian',
    'ベイブレード': 'Beyblade',
    'BEYBLADE': 'Beyblade',
    'ナノブロック': 'Nanoblock',
    'リファ': 'ReFa',
    'ReFa': 'ReFa',
    'SALONIA': 'SALONIA',
    'サロニア': 'SALONIA',
    'カタナボーイ': 'KatanaBoy',
    'ビッグボーイ': 'Bigboy',
    'ゴムボーイ': 'Gomboy',
    'ポケットボーイ': 'Pocketboy',
    'ウッドボーイ': 'Woodboy',
    'ズバット': 'Zubat',
    'ゴム太郎': 'Gomtaro',
    'スゴイ': 'Sugoi',
    '岡恒': 'Okatsune',
    '角利': 'KAKURI',
    '高儀': 'Takagi',
    'ハチェット': 'Hachette',
    'ホットウィール': 'Hot Wheels',
}

# 产品类别映射
CATEGORY_MAP = {
    '折込鋸': 'Folding Saw',
    '替刃': 'Replacement Blade',
    '携帯ケース': 'Carrying Case',
    '剪定鋏': 'Pruning Shears',
    '手帳': 'Planner',
    'プランナー': 'Planner',
    '下敷き': 'Pencil Board',
    'つめきり': 'Nail Clipper',
    '爪切り': 'Nail Clipper',
    '毛抜き': 'Tweezers',
    'はさみ': 'Scissors',
    'ハサミ': 'Scissors',
    'キッチンバサミ': 'Kitchen Scissors',
    'キッチンはさみ': 'Kitchen Scissors',
    'ボールペン': 'Ballpoint Pen',
    'ヘッドカバー': 'Headcover',
    'コーム': 'Comb',
    'ヘアコーム': 'Comb',
    'カードゲーム': 'Card Game',
    'ウノ': 'UNO',
    'UNO': 'UNO',
    'プラモデル': 'Model Kit',
    'フィギュア': 'Figure',
    'ぬいぐるみ': 'Plush',
    'イヤホン': 'Earphone',
    'ヘッドホン': 'Headphone',
    'amiibo': 'amiibo',
    'カミソリ': 'Razor',
    '替刃': 'Blade',
    'Blu-ray': 'Blu-ray',
    'CD': 'CD',
    'SHM-CD': 'CD',
}

def extract_keywords(text):
    """从文本中提取可匹配的关键词"""
    if not text:
        return set()
    
    keywords = set()
    text_upper = text.upper()
    
    # 提取品牌
    for jp, en in BRAND_MAP.items():
        if jp.upper() in text_upper or jp in text:
            keywords.add(en.upper())
    
    # 提取类别
    for jp, en in CATEGORY_MAP.items():
        if jp in text or jp.upper() in text_upper:
            keywords.add(en.upper())
    
    # 提取型号（如 338-17, 504-36, 294-30, G-1204 等）
    models = re.findall(r'[A-Z]?-?\d{2,4}[-/]\d{1,3}', text)
    for m in models:
        keywords.add(m.upper())
    
    # 提取尺寸（如 170mm, 360mm, 240mm）
    sizes = re.findall(r'\d{2,4}\s*mm', text.lower())
    for s in sizes:
        keywords.add(s.replace(' ', ''))
    
    # 提取 ASIN（如 B073XHR1X7）
    asins = re.findall(r'B[0-9A-Z]{9}', text)
    for a in asins:
        keywords.add(a)
    
    return keywords

def match_score(order_kw, purchase_kw):
    """计算匹配分数"""
    if not order_kw or not purchase_kw:
        return 0
    
    common = order_kw & purchase_kw
    if not common:
        return 0
    
    # 基础分 = 共同关键词数量
    score = len(common) * 20
    
    # 型号匹配加大分
    for kw in common:
        if re.match(r'[A-Z]?-?\d{2,4}[-/]\d{1,3}', kw):
            score += 30  # 型号匹配非常重要
        elif 'MM' in kw:
            score += 15  # 尺寸匹配较重要
    
    return min(score, 100)

def run_matching():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    
    c.execute("SELECT * FROM ebay_orders WHERE strftime('%Y-%m', sale_date) = '2026-02' ORDER BY sale_date")
    orders = c.fetchall()
    
    c.execute("SELECT * FROM purchases ORDER BY purchase_date")
    purchases = c.fetchall()
    
    print(f"📦 2 月份订单数：{len(orders)}")
    print(f"📦 全部采购数：{len(purchases)}")
    print(f"=" * 60)
    
    # 清空旧匹配
    c.execute("DELETE FROM purchase_order_links")
    
    matched = 0
    matched_details = []
    unmatched_details = []
    used_purchases = set()
    
    for order in orders:
        order_id = order['order_id']
        order_date = order['sale_date']
        order_title = order['item_title'] or ''
        
        order_kw = extract_keywords(order_title)
        
        best_match = None
        best_score = 0
        best_purchase_kw = set()
        
        for purchase in purchases:
            if purchase['id'] in used_purchases:
                continue
            
            purchase_date = purchase['purchase_date']
            purchase_name = purchase['item_name'] or ''
            
            # 日期窗口：采购日期在订单日期前 7-60 天
            if purchase_date and order_date:
                from datetime import datetime
                try:
                    p_date = datetime.strptime(purchase_date, '%Y-%m-%d')
                    o_date = datetime.strptime(order_date, '%Y-%m-%d')
                    days_diff = (o_date - p_date).days
                    if days_diff < 7 or days_diff > 60:
                        continue
                except:
                    continue
            
            purchase_kw = extract_keywords(purchase_name)
            score = match_score(order_kw, purchase_kw)
            
            if score > best_score:
                best_score = score
                best_match = purchase
                best_purchase_kw = purchase_kw
        
        if best_match and best_score >= 20:
            common_kw = order_kw & best_purchase_kw
            
            c.execute("""
                INSERT INTO purchase_order_links 
                (purchase_id, ebay_order_id, match_method, confidence, allocated_qty, allocated_cost_jpy, allocated_tax_jpy)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                best_match['id'], order_id, 'keyword',
                best_score / 100.0,
                order['quantity'],
                best_match['total_price_jpy'],
                best_match['tax_jpy']
            ))
            matched += 1
            used_purchases.add(best_match['id'])
            
            matched_details.append({
                'order': order_id,
                'ebay': order_title[:35],
                'amazon': (best_match['item_name'] or '')[:35],
                'score': best_score,
                'keywords': ', '.join(list(common_kw)[:4])
            })
            print(f"✅ {order_id} (分数:{best_score})")
            print(f"   eBay:   {order_title[:50]}")
            print(f"   Amazon: {(best_match['item_name'] or '')[:50]}")
            print(f"   关键词: {', '.join(list(common_kw)[:5])}")
        else:
            unmatched_details.append({
                'order': order_id,
                'title': order_title[:50],
                'keywords': ', '.join(list(order_kw)[:5])
            })
            print(f"❌ {order_id}: {order_title[:50]}")
            if order_kw:
                print(f"   关键词: {', '.join(list(order_kw)[:5])}")
    
    conn.commit()
    conn.close()
    
    print(f"\n{'=' * 60}")
    print(f"📊 匹配结果：{matched}/{len(orders)} ({matched/len(orders)*100:.0f}%)")
    print(f"✅ 已匹配：{matched}")
    print(f"❌ 未匹配：{len(orders) - matched}")
    
    if matched_details:
        print(f"\n{'=' * 60}")
        print(f"✅ 匹配详情：")
        for d in matched_details:
            print(f"  {d['order']}: {d['ebay']} ↔ {d['amazon']} (分数:{d['score']}, 关键词:{d['keywords']})")

if __name__ == '__main__':
    run_matching()
