"""
db/db.py — 数据库操作封装（纯 SQLite，无 ORM 依赖）
"""
import sqlite3
import os
from pathlib import Path

# schema.sql 路径（与本文件同目录）
SCHEMA_PATH = Path(__file__).parent / "schema.sql"


def get_db_path() -> str:
    """从 config.yaml 读取数据库路径，读取失败则使用默认值"""
    try:
        import yaml
        config_path = Path(__file__).parent.parent / "config.yaml"
        if config_path.exists():
            with open(config_path, "r", encoding="utf-8") as f:
                cfg = yaml.safe_load(f)
            return cfg.get("database", "data/orders.db")
    except Exception:
        pass
    return "data/orders.db"


def get_connection() -> sqlite3.Connection:
    """获取数据库连接，启用 WAL 模式和外键约束"""
    db_path = get_db_path()
    # 确保目录存在
    os.makedirs(os.path.dirname(db_path) if os.path.dirname(db_path) else ".", exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row          # 结果可按列名访问
    conn.execute("PRAGMA journal_mode=WAL") # 更好的并发性能
    conn.execute("PRAGMA foreign_keys=ON")  # 启用外键约束
    return conn


def init_db() -> None:
    """初始化数据库：读取 schema.sql 并建表（幂等，可重复执行）"""
    with open(SCHEMA_PATH, "r", encoding="utf-8") as f:
        schema_sql = f.read()
    with get_connection() as conn:
        conn.executescript(schema_sql)
        # 迁移：为已存在的表添加新列（ALTER TABLE IF NOT EXISTS column 不支持，需手动检查）
        _migrate(conn)
    print(f"[db] 数据库初始化完成: {get_db_path()}")


def _migrate(conn: sqlite3.Connection) -> None:
    """运行增量迁移（幂等）"""
    # ebay_orders 迁移
    cols = {row[1] for row in conn.execute("PRAGMA table_info(ebay_orders)").fetchall()}
    if "tracking_number" not in cols:
        conn.execute("ALTER TABLE ebay_orders ADD COLUMN tracking_number TEXT")
        print("[db] 迁移：ebay_orders 添加 tracking_number 列")

    # purchases 迁移：添加 no_match_reason
    cols = {row[1] for row in conn.execute("PRAGMA table_info(purchases)").fetchall()}
    if "no_match_reason" not in cols:
        conn.execute("ALTER TABLE purchases ADD COLUMN no_match_reason TEXT DEFAULT NULL")
        print("[db] 迁移：purchases 添加 no_match_reason 列")

    # shipments 迁移：添加 match_method 和 confirmed_by
    cols = {row[1] for row in conn.execute("PRAGMA table_info(shipments)").fetchall()}
    if "match_method" not in cols:
        conn.execute("ALTER TABLE shipments ADD COLUMN match_method TEXT DEFAULT NULL")
        print("[db] 迁移：shipments 添加 match_method 列")
    if "confirmed_by" not in cols:
        conn.execute("ALTER TABLE shipments ADD COLUMN confirmed_by TEXT DEFAULT NULL")
        print("[db] 迁移：shipments 添加 confirmed_by 列")

    # purchase_order_links 迁移：添加 confirmed_by
    cols = {row[1] for row in conn.execute("PRAGMA table_info(purchase_order_links)").fetchall()}
    if "confirmed_by" not in cols:
        conn.execute("ALTER TABLE purchase_order_links ADD COLUMN confirmed_by TEXT DEFAULT NULL")
        print("[db] 迁移：purchase_order_links 添加 confirmed_by 列")


# ---------- 通用 CRUD 工具函数 ----------

def insert(table: str, data: dict) -> None:
    """插入一条记录。data 为 {列名: 值} 字典"""
    cols = ", ".join(data.keys())
    placeholders = ", ".join(["?"] * len(data))
    sql = f"INSERT OR IGNORE INTO {table} ({cols}) VALUES ({placeholders})"
    with get_connection() as conn:
        conn.execute(sql, list(data.values()))


def insert_many(table: str, rows: list[dict]) -> int:
    """批量插入，返回实际插入的行数"""
    if not rows:
        return 0
    cols = ", ".join(rows[0].keys())
    placeholders = ", ".join(["?"] * len(rows[0]))
    sql = f"INSERT OR IGNORE INTO {table} ({cols}) VALUES ({placeholders})"
    with get_connection() as conn:
        cursor = conn.executemany(sql, [list(r.values()) for r in rows])
        return cursor.rowcount


def fetch_all(sql: str, params: tuple = ()) -> list[dict]:
    """执行查询，返回 list[dict]"""
    with get_connection() as conn:
        rows = conn.execute(sql, params).fetchall()
    return [dict(r) for r in rows]


def fetch_one(sql: str, params: tuple = ()) -> dict | None:
    """执行查询，返回单行 dict 或 None"""
    with get_connection() as conn:
        row = conn.execute(sql, params).fetchone()
    return dict(row) if row else None


def execute(sql: str, params: tuple = ()) -> int:
    """执行 UPDATE / DELETE，返回影响行数"""
    with get_connection() as conn:
        cursor = conn.execute(sql, params)
        return cursor.rowcount


def count(table: str, where: str = "", params: tuple = ()) -> int:
    """统计表中行数，可附加 WHERE 条件"""
    sql = f"SELECT COUNT(*) FROM {table}"
    if where:
        sql += f" WHERE {where}"
    with get_connection() as conn:
        return conn.execute(sql, params).fetchone()[0]
