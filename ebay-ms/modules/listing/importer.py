"""
CSV/Excel 批量导入上新模块。

支持：
- 读取 CSV 或 XLSX 文件
- Pydantic 逐行校验
- 中断续传（按 batch_progress 表记录已处理行号）
- 批量创建 listing（单品 + 变体）
- 详细的成功/失败报告

使用方式：
    result = ListingImporter().import_file("products.csv")
    print(result.summary())
"""

from __future__ import annotations

import csv
import io
import os
from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING, Any, Iterable

from core.database.connection import get_session
from loguru import logger as log
from modules.listing.schemas import VariantSpecific
from modules.listing.service import ListingService
from modules.listing.template_service import TemplateService

if TYPE_CHECKING:
    pass


# ── CSV Row Schema ──────────────────────────────────────────────────────────

@dataclass
class ImportRow:
    """CSV 一行数据。字段名与 CSV 表头对应。"""
    sku: str
    title: str
    description: str | None = None
    category_id: str | None = None
    condition: str = "NEW"
    condition_description: str | None = None
    listing_price: float | None = None
    quantity: int | None = None
    image_urls: str | None = None   # 逗号分隔
    fulfillment_policy_id: str | None = None
    return_policy_id: str | None = None
    payment_policy_id: str | None = None
    template_id: str | None = None   # 可选：引用模板覆盖以上字段
    # 变体字段
    variant_sku: str | None = None
    variant_specifics: str | None = None  # "Size:M,Color:Red" 格式
    is_parent: bool = False  # 变体父行


@dataclass
class ImportResult:
    """批量导入结果。"""
    total_rows: int = 0
    success_count: int = 0
    failure_count: int = 0
    errors: list[ImportError] = field(default_factory=list)
    # 中断续传
    batch_id: str | None = None
    last_processed_row: int = -1
    completed: bool = False

    def summary(self) -> str:
        return (
            f"导入完成：{self.success_count}/{self.total_rows} 成功，"
            f"{self.failure_count} 失败"
        )


@dataclass
class ImportError:
    """单行导入错误。"""
    row: int
    sku: str
    message: str


# ── ListingImporter ──────────────────────────────────────────────────────────

class ListingImporter:
    """批量导入上新。"""

    def __init__(
        self,
        batch_id: str | None = None,
        resume: bool = True,
    ) -> None:
        """
        Args:
            batch_id: 批次 ID，用于中断续传。不传则自动生成。
            resume: 是否从上次中断处继续（读取 batch_progress 表）。
        """
        self.listing_service = ListingService()
        self.template_service = TemplateService()
        self.batch_id = batch_id or _generate_batch_id()
        self.resume = resume
        self._start_offset = 0

        if resume:
            self._start_offset = self._load_progress()

    # ── 公共方法 ──────────────────────────────────────────────────────────

    def import_file(
        self,
        file_path: str,
        *,
        skip_header: bool = True,
    ) -> ImportResult:
        """从 CSV/XLSX 文件导入。

        Args:
            file_path: 文件路径。
            skip_header: 是否跳过第一行（表头）。

        Returns:
            ImportResult。
        """
        ext = os.path.splitext(file_path)[1].lower()
        if ext == ".csv":
            rows = self._read_csv(file_path, skip_header=skip_header)
        elif ext in (".xlsx", ".xls"):
            rows = self._read_excel(file_path, skip_header=skip_header)
        else:
            raise ValueError(f"不支持的文件格式: {ext}，仅支持 CSV/XLSX")

        return self.import_rows(rows)

    def import_rows(
        self,
        rows: Iterable[ImportRow | dict[str, Any]],
    ) -> ImportResult:
        """导入行数据（支持 dict 或 ImportRow）。"""

        # 将 dict 统一转为 ImportRow
        parsed: list[tuple[int, ImportRow]] = []
        for i, row in enumerate(rows):
            offset_i = i + self._start_offset
            if isinstance(row, dict):
                row = self._dict_to_row(row)
            parsed.append((offset_i, row))

        result = ImportResult(total_rows=len(parsed), batch_id=self.batch_id)
        result.last_processed_row = self._start_offset - 1

        # Group rows by parent for variant handling
        parent_map: dict[str, list[ImportRow]] = {}
        single_rows: list[tuple[int, ImportRow]] = []

        for i, row in parsed:
            if row.is_parent or row.variant_sku:
                # 变体模式：以 parent sku 为 key 分组
                parent_sku = row.sku
                parent_map.setdefault(parent_sku, [])
                parent_map[parent_sku].append(row)
            else:
                single_rows.append((i, row))

        # 处理单品
        for i, row in single_rows:
            try:
                self._process_single(row, i)
                result.success_count += 1
                result.last_processed_row = i
                self._save_progress(i)
            except Exception as exc:
                result.failure_count += 1
                result.errors.append(ImportError(row=i, sku=row.sku, message=str(exc)))
                log.warning(f"Row {i} 失败 sku={row.sku}: {exc}")

        # 处理变体（以 parent sku 为单位）
        for parent_sku, variant_rows in parent_map.items():
            try:
                self._process_variant(parent_sku, variant_rows, result)
                # 更新 last_processed_row
                max_i = max(i for i, r in parsed if r.sku in {pr.sku for pr in variant_rows})
                result.last_processed_row = max_i
                self._save_progress(max_i)
            except Exception as exc:
                result.failure_count += len(variant_rows)
                for r in variant_rows:
                    result.errors.append(ImportError(row=parsed.index((0, r)), sku=r.sku, message=str(exc)))
                log.warning(f"Variant group {parent_sku} 失败: {exc}")

        result.completed = True
        self._clear_progress()
        return result

    def generate_template(self, file_path: str | None = None) -> str:
        """生成空白导入模板 CSV。"""
        headers = [
            "sku", "title", "description", "category_id",
            "condition", "condition_description",
            "listing_price", "quantity", "image_urls",
            "fulfillment_policy_id", "return_policy_id", "payment_policy_id",
            "template_id",
            "variant_sku", "variant_specifics", "is_parent",
        ]
        sample_rows = [
            ["SKU001", "商品标题示例", "商品描述", "257777", "NEW", "全新未拆封",
             "3500", "10", "https://example.com/img1.jpg,https://example.com/img2.jpg",
             "", "", "", "", "", "", "FALSE"],
            ["SKU002-V-M", "尺码 M 变体", "", "", "", "",
             "3200", "5", "", "", "", "", "PARENT-SKU", "Size:M", "FALSE"],
        ]

        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(headers)
        writer.writerows(sample_rows)

        content = output.getvalue()
        if file_path:
            with open(file_path, "w", newline="", encoding="utf-8") as f:
                f.write(content)
            log.info(f"模板已生成: {file_path}")

        return content

    # ── 私有方法 ──────────────────────────────────────────────────────────

    def _dict_to_row(self, d: dict[str, Any]) -> ImportRow:
        """将字典转为 ImportRow，处理类型转换。"""
        def _float(v: Any) -> float | None:
            if v is None or v == "":
                return None
            try:
                return float(str(v))
            except (ValueError, TypeError):
                return None

        def _int(v: Any) -> int | None:
            if v is None or v == "":
                return None
            try:
                return int(str(v))
            except (ValueError, TypeError):
                return None

        def _str(v: Any) -> str | None:
            if v is None:
                return None
            s = str(v).strip()
            return s if s else None

        return ImportRow(
            sku=_str(d.get("sku")) or "",
            title=_str(d.get("title")) or "",
            description=_str(d.get("description")),
            category_id=_str(d.get("category_id")),
            condition=_str(d.get("condition")) or "NEW",
            condition_description=_str(d.get("condition_description")),
            listing_price=_float(d.get("listing_price")),
            quantity=_int(d.get("quantity")),
            image_urls=_str(d.get("image_urls")),
            fulfillment_policy_id=_str(d.get("fulfillment_policy_id")),
            return_policy_id=_str(d.get("return_policy_id")),
            payment_policy_id=_str(d.get("payment_policy_id")),
            template_id=_str(d.get("template_id")),
            variant_sku=_str(d.get("variant_sku")),
            variant_specifics=_str(d.get("variant_specifics")),
            is_parent=str(d.get("is_parent", "")).upper() in ("TRUE", "1", "YES"),
        )

    def _process_single(self, row: ImportRow, row_index: int) -> None:
        """处理单个商品 listing。"""
        from modules.listing.schemas import ListingCreateRequest

        if not row.sku or not row.title:
            raise ValueError("sku 和 title 为必填字段")

        # 如果指定了模板，应用模板
        if row.template_id:
            product = _mock_product_from_row(row)
            req = self.template_service.apply_template(
                template_id=row.template_id,
                product=product,
                price=row.listing_price or 0,
                quantity=row.quantity or 0,
                condition=row.condition,
                image_urls=self._parse_image_urls(row.image_urls),
            )
        else:
            req = ListingCreateRequest(
                sku=row.sku,
                title=row.title,
                description=row.description or "",
                category_id=row.category_id or "",
                condition=row.condition,
                condition_description=row.condition_description,
                listing_price=row.listing_price or 0,
                quantity=row.quantity or 0,
                image_urls=self._parse_image_urls(row.image_urls),
                fulfillment_policy_id=row.fulfillment_policy_id or "",
                return_policy_id=row.return_policy_id or "",
                payment_policy_id=row.payment_policy_id or "",
                currency="USD",
                marketplace_id="EBAY_US",
            )

        self.listing_service.create_single_listing(req)
        log.info(f"Row {row_index} 创建成功: sku={row.sku}")

    def _process_variant(
        self,
        parent_sku: str,
        variant_rows: list[ImportRow],
        result: ImportResult,
    ) -> None:
        """处理变体组。"""
        from modules.listing.schemas import (
            InventoryItemGroupRequest,
            VariantItem,
        )

        # 解析 variant_specifics
        variants: list[VariantItem] = []
        for vr in variant_rows:
            specifics = self._parse_variant_specifics(vr.variant_specifics or "")
            if not specifics:
                continue
            variants.append(VariantItem(
                sku=vr.sku,
                price=vr.listing_price or 0,
                quantity=vr.quantity or 0,
                variant_specifics=specifics,
            ))

        if len(variants) < 2:
            raise ValueError(f"变体 listing 至少需要 2 个变体，当前 {len(variants)} 个")

        # 取第一个变体的描述作为 group 描述
        first = variant_rows[0]
        group_title = first.title or f"变体商品 {parent_sku}"

        req = InventoryItemGroupRequest(
            group_title=group_title,
            group_description=first.description or "",
            category_id=first.category_id or "",
            condition=first.condition or "NEW",
            image_urls=self._parse_image_urls(first.image_urls),
            variants=variants,
            fulfillment_policy_id=first.fulfillment_policy_id or None,
            return_policy_id=first.return_policy_id or None,
            payment_policy_id=first.payment_policy_id or None,
            template_id=first.template_id,
        )

        resp = self.listing_service.create_variant_listing(req)
        if not resp.success:
            raise RuntimeError(f"变体创建失败: {resp.errors}")
        result.success_count += 1
        log.info(f"Variant group 创建成功: parent={parent_sku}, variants={len(variants)}")

    def _parse_image_urls(self, urls_str: str | None) -> list[str]:
        if not urls_str:
            return []
        return [u.strip() for u in urls_str.split(",") if u.strip()]

    def _parse_variant_specifics(self, spec_str: str) -> list[VariantSpecific]:
        """解析 'Size:M,Color:Red' 格式。"""
        result: list[VariantSpecific] = []
        if not spec_str:
            return result
        for pair in spec_str.split(","):
            pair = pair.strip()
            if ":" in pair:
                name, value = pair.split(":", 1)
                result.append(VariantSpecific(name=name.strip(), value=value.strip()))
        return result

    def _read_csv(self, file_path: str, skip_header: bool) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        with open(file_path, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            if skip_header and reader.fieldnames:
                pass  # DictReader 自动跳过
            for row in reader:
                rows.append(dict(row))
        return rows

    def _read_excel(self, file_path: str, skip_header: bool) -> list[dict[str, Any]]:
        import openpyxl
        wb = openpyxl.load_workbook(file_path, read_only=True, data_only=True)
        ws = wb.active
        raw_rows = list(ws.iter_rows(values_only=True))
        wb.close()

        if not raw_rows:
            return []

        if skip_header:
            header = [str(c) if c is not None else "" for c in raw_rows[0]]
            data_rows = raw_rows[1:]
        else:
            header = [f"col_{i}" for i in range(len(raw_rows[0]))]
            data_rows = raw_rows

        result: list[dict[str, Any]] = []
        for row in data_rows:
            result.append({header[i]: (str(cell) if cell is not None else "") for i, cell in enumerate(row)})
        return result

    # ── 中断续传 ──────────────────────────────────────────────────────────

    def _load_progress(self) -> int:
        """从数据库读取已处理的行号。"""
        if not self.batch_id:
            return 0
        try:
            with get_session() as sess:
                from core.models.batch import BatchProgress
                bp = sess.query(BatchProgress).filter(
                    BatchProgress.batch_id == self.batch_id
                ).first()
                if bp:
                    log.info(f"从 batch_id={self.batch_id} 恢复，行号={bp.last_row}")
                    return bp.last_row + 1
        except Exception:
            pass
        return 0

    def _save_progress(self, row_index: int) -> None:
        """保存当前进度。"""
        if not self.batch_id:
            return
        try:
            with get_session() as sess:
                from core.models.batch import BatchProgress
                bp = sess.query(BatchProgress).filter(
                    BatchProgress.batch_id == self.batch_id
                ).first()
                if bp:
                    bp.last_row = row_index
                    bp.updated_at = datetime.now()
                else:
                    bp = BatchProgress(
                        batch_id=self.batch_id,
                        last_row=row_index,
                    )
                    sess.add(bp)
                sess.commit()
        except Exception as exc:
            log.warning(f"保存进度失败（非阻塞）: {exc}")

    def _clear_progress(self) -> None:
        """完成后清除进度记录。"""
        if not self.batch_id:
            return
        try:
            with get_session() as sess:
                from core.models.batch import BatchProgress
                sess.query(BatchProgress).filter(
                    BatchProgress.batch_id == self.batch_id
                ).delete()
                sess.commit()
        except Exception:
            pass


# ── helpers ─────────────────────────────────────────────────────────────────

def _generate_batch_id() -> str:
    from datetime import datetime as dt
    return f"batch_{dt.now().strftime('%Y%m%d_%H%M%S')}"


def _mock_product_from_row(row: ImportRow):
    """从 ImportRow 构造一个 mock Product（用于 apply_template）。"""
    class _MockProduct:
        sku = row.sku
        title = row.title
        brand = ""
    return _MockProduct()
