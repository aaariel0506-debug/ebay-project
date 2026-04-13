"""
每日自动备份脚本
复制数据库文件到 backups/ 目录，保留最近 7 天。
"""
import shutil
import sys
from datetime import datetime
from pathlib import Path

# 将项目根加入 path，以便导入 core
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.config.settings import settings


def run_backup() -> None:
    settings.BACKUP_DIR.mkdir(parents=True, exist_ok=True)

    db_path = settings.db_path
    if not db_path.exists():
        print(f"[backup] 数据库文件不存在: {db_path}，跳过。")
        return

    today = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    backup_name = f"ebay_{today}.db"
    backup_path = settings.BACKUP_DIR / backup_name

    shutil.copy2(db_path, backup_path)
    print(f"[backup] ✓ 备份已创建: {backup_path}")

    # 清理旧备份（保留最近 N 天）
    cutoff = datetime.now().timestamp() - settings.BACKUP_RETENTION_DAYS * 86400
    removed = 0
    for f in settings.BACKUP_DIR.glob("ebay_*.db"):
        if f.stat().st_mtime < cutoff:
            f.unlink()
            removed += 1
    if removed:
        print(f"[backup] 已清理 {removed} 个旧备份（>{settings.BACKUP_RETENTION_DAYS}天）")

    # 列出当前备份
    backups = sorted(settings.BACKUP_DIR.glob("ebay_*.db"))
    print(f"[backup] 当前备份数: {len(backups)}")
    for b in backups[-5:]:
        print(f"  - {b.name}")


if __name__ == "__main__":
    run_backup()
