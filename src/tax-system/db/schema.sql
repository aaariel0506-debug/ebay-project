-- eBay Tax System — 数据库表结构

-- 采购记录
CREATE TABLE IF NOT EXISTS purchases (
    id TEXT PRIMARY KEY,
    platform TEXT NOT NULL,           -- amazon_jp / hobonichi / bandai / offline / other
    purchase_date DATE,
    item_name TEXT,
    item_name_en TEXT,
    item_sku TEXT,
    quantity INTEGER DEFAULT 1,
    unit_price_jpy REAL,
    total_price_jpy REAL,
    tax_jpy REAL,
    shipping_fee_jpy REAL,
    order_number TEXT,
    receipt_image_path TEXT,          -- 线下领收书照片路径
    needs_review INTEGER DEFAULT 0,   -- OCR 低置信度，需人工复核
    no_match_reason TEXT DEFAULT NULL,-- 无匹配原因：'no_ebay_order' | NULL
    notes TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- eBay 订单
CREATE TABLE IF NOT EXISTS ebay_orders (
    order_id TEXT PRIMARY KEY,
    sale_date DATE,
    buyer_username TEXT,
    item_title TEXT,
    item_id TEXT,
    quantity INTEGER DEFAULT 1,
    sale_price_usd REAL,
    shipping_charged_usd REAL,
    ebay_fee_usd REAL,
    ebay_ad_fee_usd REAL,
    payment_net_usd REAL,
    order_status TEXT,
    shipping_address_country TEXT,
    tracking_number TEXT,              -- eBay 上的快递单号（用于匹配 CPass Order No.）
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 快递记录
CREATE TABLE IF NOT EXISTS shipments (
    id TEXT PRIMARY KEY,
    carrier TEXT,                      -- cpass_speedpak / cpass_fedex / japanpost
    tracking_number TEXT,
    ebay_order_id TEXT,                -- 关联 eBay 订单（可为空，待匹配）
    ship_date DATE,
    shipping_fee_usd REAL,
    cpass_transaction_id TEXT,
    jp_post_email_path TEXT,           -- Japan Post 邮件文件路径
    match_method TEXT DEFAULT NULL,    -- auto / manual / NULL
    confirmed_by TEXT DEFAULT NULL,    -- 'auto' | 'user' | NULL
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (ebay_order_id) REFERENCES ebay_orders(order_id)
);

-- 采购 - 订单匹配关系
CREATE TABLE IF NOT EXISTS purchase_order_links (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    purchase_id TEXT NOT NULL,
    ebay_order_id TEXT NOT NULL,
    match_method TEXT,                 -- sku / fuzzy / date_price / manual
    confidence REAL,                   -- 匹配置信度 0~1
    confirmed_by TEXT DEFAULT NULL,    -- 'auto' | 'user' | NULL
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (purchase_id) REFERENCES purchases(id),
    FOREIGN KEY (ebay_order_id) REFERENCES ebay_orders(order_id)
);

-- 索引
CREATE INDEX IF NOT EXISTS idx_purchases_date ON purchases(purchase_date);
CREATE INDEX IF NOT EXISTS idx_purchases_platform ON purchases(platform);
CREATE INDEX IF NOT EXISTS idx_ebay_orders_date ON ebay_orders(sale_date);
CREATE INDEX IF NOT EXISTS idx_shipments_order ON shipments(ebay_order_id);
CREATE INDEX IF NOT EXISTS idx_shipments_tracking ON shipments(tracking_number);
