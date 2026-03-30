"""
db/migrate.py — 数据库迁移脚本

用于添加 v2 匹配所需的新字段和表
"""
from db.db import execute, fetch_one


def migrate_v2():
    """
    执行 v2 迁移：
    1. 添加 purchase_order_links 新字段
    2. 创建 inventory 表
    """
    print("🔄 开始数据库迁移 v2...")
    
    # 检查是否已迁移
    existing = fetch_one("""
        SELECT name FROM sqlite_master 
        WHERE type='table' AND name='inventory'
    """)
    
    if existing:
        print("✅ 数据库已是最新版本")
        return
    
    # 1. 添加 purchase_order_links 新字段
    print("  📝 添加 purchase_order_links 字段...")
    
    try:
        execute("ALTER TABLE purchase_order_links ADD COLUMN allocated_qty INTEGER DEFAULT NULL")
        print("    ✓ allocated_qty")
    except Exception as e:
        if "duplicate column" not in str(e).lower():
            raise
    
    try:
        execute("ALTER TABLE purchase_order_links ADD COLUMN allocated_cost_jpy REAL DEFAULT NULL")
        print("    ✓ allocated_cost_jpy")
    except Exception as e:
        if "duplicate column" not in str(e).lower():
            raise
    
    try:
        execute("ALTER TABLE purchase_order_links ADD COLUMN allocated_tax_jpy REAL DEFAULT NULL")
        print("    ✓ allocated_tax_jpy")
    except Exception as e:
        if "duplicate column" not in str(e).lower():
            raise
    
    # 2. 创建 inventory 表
    print("  📦 创建 inventory 表...")
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
    print("    ✓ inventory 表已创建")
    
    # 3. 创建索引
    print("  📇 创建索引...")
    execute("CREATE INDEX IF NOT EXISTS idx_inventory_sku ON inventory(item_sku)")
    execute("CREATE INDEX IF NOT EXISTS idx_pol_allocated ON purchase_order_links(allocated_qty)")
    print("    ✓ 索引已创建")
    
    print("✅ 数据库迁移 v2 完成！")


if __name__ == "__main__":
    migrate_v2()
