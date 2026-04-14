"""scripts.migrate.base_migrator — 迁移基类

迁移流程：pre_check → migrate → post_check → rollback（如需）

用法：
    class MyMigrator(BaseMigrator):
        name = "my_data"
        model = MyModel

        def pre_check(self) -> bool:
            ...

        def transform(self, raw: dict) -> dict:
            ...

        def post_check(self, count: int) -> bool:
            ...

    migrator = MyMigrator(source_path="data.xlsx")
    migrator.run()
"""

import abc
from dataclasses import dataclass, field
from pathlib import Path

from loguru import logger

log = logger.bind(task="migration")


@dataclass
class MigrationResult:
    """迁移结果"""
    success: bool
    name: str
    total: int = 0
    imported: int = 0
    skipped: int = 0
    errors: list[dict] = field(default_factory=list)

    def summary(self) -> str:
        return (
            f"[{self.name}] "
            f"imported={self.imported}/{self.total} "
            f"skipped={self.skipped} "
            f"errors={len(self.errors)}"
        )


class BaseMigrator(abc.ABC):
    """
    数据迁移基类

    子类实现：
        name        — 迁移名称
        model       — SQLAlchemy 模型类
        pre_check() — 迁移前检查（返回 bool）
        transform() — 将原始 dict 转换为模型可接受的 dict
        post_check() — 迁移后验证（返回 bool）
    """

    name: str = "base"
    batch_size: int = 100

    def __init__(self, source_path: str | Path | None = None):
        self.source_path = Path(source_path) if source_path else None
        self.result = MigrationResult(success=False, name=self.name)
        self._setup_logging()

    def _setup_logging(self) -> None:
        log.info(f"初始化迁移任务: {self.name}")

    # ── 生命周期（子类可override） ──────────────────────────

    def pre_check(self) -> bool:
        """迁移前检查。返回 True 继续，False 终止"""
        return True

    @abc.abstractmethod
    def transform(self, raw: dict) -> dict:
        """将原始数据 dict 转换为模型字段 dict"""
        ...

    def post_check(self, count: int) -> bool:
        """迁移后验证。返回 True 表示通过，False 触发 rollback 提示"""
        return True

    def rollback(self, imported_ids: list) -> None:
        """回滚已导入的记录（子类可实现具体逻辑）"""
        log.warning(f"[{self.name}] 回滚已导入的 {len(imported_ids)} 条记录")

    # ── 核心运行逻辑 ────────────────────────────────────────

    def run(self, records: list[dict]) -> MigrationResult:
        """
        执行迁移主流程：

        1. pre_check() — 前置检查
        2. 逐条 transform() + 保存
        3. post_check() — 后置验证
        4. 如验证失败 → rollback()
        """
        self.result.total = len(records)

        if not self.pre_check():
            log.error(f"[{self.name}] pre_check 失败，迁移终止")
            self.result.success = False
            return self.result

        log.info(f"[{self.name}] 开始迁移 {len(records)} 条记录")

        imported_ids: list = []

        for i, raw in enumerate(records):
            try:
                transformed = self.transform(raw)
                self._save(transformed)
                imported_ids.append(transformed.get("id"))
                self.result.imported += 1
            except Exception as exc:
                self.result.errors.append({
                    "index": i,
                    "data": raw,
                    "error": str(exc),
                })
                self.result.skipped += 1
                log.error(f"[{self.name}] 第 {i} 条失败: {exc}")

            if (i + 1) % self.batch_size == 0:
                log.debug(f"[{self.name}] 已处理 {i+1}/{len(records)} 条")

        if not self.post_check(self.result.imported):
            log.error(f"[{self.name}] post_check 失败，触发回滚")
            self.rollback(imported_ids)
            self.result.success = False
            return self.result

        self.result.success = True
        log.info(f"[{self.name}] 完成: {self.result.summary()}")
        return self.result

    def _save(self, data: dict) -> None:
        """保存单条记录到数据库（可override）"""
        from core.database.connection import get_session

        model = self.model
        with get_session() as s:
            instance = model(**data)
            s.add(instance)
            s.commit()
