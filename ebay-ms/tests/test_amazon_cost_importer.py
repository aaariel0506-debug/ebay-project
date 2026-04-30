"""
tests/test_amazon_cost_importer.py
AmazonCostImporter 单元测试（Brief 2）
"""
from __future__ import annotations

import csv
from datetime import date
from decimal import Decimal
from io import StringIO
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from core.models import Product, ProductStatus, SupplierPriceHistory
from core.models.base import Base
from modules.finance.amazon_cost_importer import AmazonCostImporter


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def in_memory_db(tmp_path: Path) -> Session:
    """独立的内存 SQLite 数据库，隔离测试。"""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as sess:
        yield sess


@pytest.fixture
def output_dir(tmp_path: Path) -> Path:
    return tmp_path / "imports"


def make_amazon_csv(path: Path, rows: list[dict]) -> Path:
    """生成最简 Amazon CSV，匹配真实 CSV 列结构。

    真实 CSV 列（部分）:
      注文日, ASIN, 注文の数量, 商品の小計（税込）, 商品名
    ASIN 格式为 ="B0XXXXX"（真实 Amazon 导出格式）。
    """
    header = [
        "注文日", "注文番号", "アカウントグループ", "発注番号",
        "注文の数量", "通貨", "注文の小計（税抜）",
        "注文の配送料および手数料（税抜）", "注文の消費税額",
        "注文の割引（税込）", "注文の合計（税込）",
        "ASIN", "商品名",
        "商品の小計（税込）", "商品の小計（税抜）",
    ]
    asin_col = header.index("ASIN")
    qty_col = header.index("注文の数量")
    amt_col = header.index("商品の小計（税込）")
    title_col = header.index("商品名")
    date_col = header.index("注文日")

    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(header)
        for r in rows:
            row = [""] * len(header)
            row[date_col] = r.get("date", "2026/04/01")
            row[asin_col] = f'="{r.get("asin", "")}"'
            row[qty_col] = r.get("qty", 1)
            row[amt_col] = r.get("amount", 1000)
            row[title_col] = r.get("title", "Test Product")
            writer.writerow(row)
    return path


# ── AmazonCostImporter 主类测试 ────────────────────────────────────────────────

class TestAmazonCostImporter:
    """核心 upsert 逻辑测试。"""

    def test_one_to_one_upsert_success(self, in_memory_db: Session, tmp_path: Path):
        """1-to-1 映射 → Product.cost_price 被正确填充。"""
        # 先建 Product（通过 listing importer 流程，这里直接建）
        in_memory_db.add(Product(
            sku="SKU-001",
            title=None,
            asin="B0ABCDEF12",
            source_url="https://www.amazon.co.jp/dp/B0ABCDEF12",
            cost_price=None,
            cost_currency="JPY",
            status=ProductStatus.ACTIVE,
        ))
        in_memory_db.commit()

        csv_path = make_amazon_csv(tmp_path / "test.csv", [
            {"asin": "B0ABCDEF12", "qty": 2, "amount": 3000, "title": "Test A"},
        ])

        with patch("modules.finance.amazon_cost_importer.get_session") as mock_sess:
            mock_sess.return_value.__enter__ = MagicMock(return_value=in_memory_db)
            mock_sess.return_value.__exit__ = MagicMock(return_value=False)
            importer = AmazonCostImporter(output_dir=tmp_path / "out")
            result = importer.import_csv(csv_path)

        assert result.cost_upserted == 1
        assert result.ambiguous == 0
        assert result.unmapped == 0
        p = in_memory_db.get(Product, "SKU-001")
        assert p.cost_price == Decimal("1500.00")   # 3000 / 2

    def test_existing_cost_history_written(self, in_memory_db: Session, tmp_path: Path):
        """已有 cost_price → 旧值写入 SupplierPriceHistory。"""
        in_memory_db.add(Product(
            sku="SKU-002",
            title=None,
            asin="B0BBB22222",
            source_url="https://www.amazon.co.jp/dp/B0BBB22222",
            cost_price=Decimal("1000.00"),
            cost_currency="JPY",
            status=ProductStatus.ACTIVE,
        ))
        in_memory_db.commit()

        csv_path = make_amazon_csv(tmp_path / "test.csv", [
            {"asin": "B0BBB22222", "qty": 1, "amount": 2000, "title": "Test B"},
        ])

        with patch("modules.finance.amazon_cost_importer.get_session") as mock_sess:
            mock_sess.return_value.__enter__ = MagicMock(return_value=in_memory_db)
            mock_sess.return_value.__exit__ = MagicMock(return_value=False)
            importer = AmazonCostImporter(output_dir=tmp_path / "out")
            result = importer.import_csv(csv_path)

        assert result.cost_upserted == 1
        # 旧值进了历史
        hist = in_memory_db.query(SupplierPriceHistory).filter_by(sku="SKU-002").all()
        assert len(hist) == 1
        assert hist[0].price == Decimal("1000.00")
        # 新值覆盖了 product
        p = in_memory_db.get(Product, "SKU-002")
        assert p.cost_price == Decimal("2000.00")

    def test_idempotent_second_run_writes_history(self, in_memory_db: Session, tmp_path: Path):
        """同 SKU 跑两次 → 第二次旧值进历史。"""
        # 第一次运行
        in_memory_db.add(Product(
            sku="SKU-IDEM",
            title=None,
            asin="B0IDEM0001",
            source_url="https://www.amazon.co.jp/dp/B0IDEM0001",
            cost_price=None,
            cost_currency="JPY",
            status=ProductStatus.ACTIVE,
        ))
        in_memory_db.commit()

        csv1 = make_amazon_csv(tmp_path / "run1.csv", [
            {"asin": "B0IDEM0001", "qty": 1, "amount": 1000, "title": "Run 1"},
        ])

        with patch("modules.finance.amazon_cost_importer.get_session") as mock_sess:
            mock_sess.return_value.__enter__ = MagicMock(return_value=in_memory_db)
            mock_sess.return_value.__exit__ = MagicMock(return_value=False)
            importer = AmazonCostImporter(output_dir=tmp_path / "out")
            importer.import_csv(csv1)

        # 第二次运行（cost_price 已有值）
        csv2 = make_amazon_csv(tmp_path / "run2.csv", [
            {"asin": "B0IDEM0001", "qty": 1, "amount": 1500, "title": "Run 2"},
        ])

        with patch("modules.finance.amazon_cost_importer.get_session") as mock_sess:
            mock_sess.return_value.__enter__ = MagicMock(return_value=in_memory_db)
            mock_sess.return_value.__exit__ = MagicMock(return_value=False)
            importer = AmazonCostImporter(output_dir=tmp_path / "out")
            result = importer.import_csv(csv2)

        assert result.cost_upserted == 1
        hist = in_memory_db.query(SupplierPriceHistory).filter_by(sku="SKU-IDEM").all()
        assert len(hist) == 1
        assert hist[0].price == Decimal("1000.00")   # 第一次的值
        p = in_memory_db.get(Product, "SKU-IDEM")
        assert p.cost_price == Decimal("1500.00")   # 第二次的值

    def test_ambiguous_asin_writes_csv(self, in_memory_db: Session, tmp_path: Path):
        """多 SKU 共享 ASIN → ambiguous_costs.csv，DB 不变。"""
        # 两个 SKU 共用同一个 ASIN
        in_memory_db.add(Product(
            sku="SKU-A1",
            title=None,
            asin="B0AMBIGU01",
            source_url="https://www.amazon.co.jp/dp/B0AMBIGU01",
            cost_price=None,
            cost_currency="JPY",
            status=ProductStatus.ACTIVE,
        ))
        in_memory_db.add(Product(
            sku="SKU-A2",
            title=None,
            asin="B0AMBIGU01",
            source_url="https://www.amazon.co.jp/dp/B0AMBIGU01",
            cost_price=None,
            cost_currency="JPY",
            status=ProductStatus.ACTIVE,
        ))
        in_memory_db.commit()

        csv_path = make_amazon_csv(tmp_path / "test.csv", [
            {"asin": "B0AMBIGU01", "qty": 2, "amount": 3000, "title": "Ambiguous"},
        ])

        out_dir = tmp_path / "out"
        with patch("modules.finance.amazon_cost_importer.get_session") as mock_sess:
            mock_sess.return_value.__enter__ = MagicMock(return_value=in_memory_db)
            mock_sess.return_value.__exit__ = MagicMock(return_value=False)
            importer = AmazonCostImporter(output_dir=out_dir)
            result = importer.import_csv(csv_path)

        assert result.ambiguous == 1
        assert result.cost_upserted == 0
        assert (out_dir / "ambiguous_costs.csv").exists()
        # 两 SKU 仍未有 cost_price
        assert in_memory_db.get(Product, "SKU-A1").cost_price is None
        assert in_memory_db.get(Product, "SKU-A2").cost_price is None

    def test_unmapped_asin_writes_csv(self, in_memory_db: Session, tmp_path: Path):
        """ASIN 不在 products 表 → unmapped_asins.csv。"""
        csv_path = make_amazon_csv(tmp_path / "test.csv", [
            {"asin": "B0UNMAPPED", "qty": 1, "amount": 999, "title": "Not Found"},
        ])

        out_dir = tmp_path / "out"
        with patch("modules.finance.amazon_cost_importer.get_session") as mock_sess:
            mock_sess.return_value.__enter__ = MagicMock(return_value=in_memory_db)
            mock_sess.return_value.__exit__ = MagicMock(return_value=False)
            importer = AmazonCostImporter(output_dir=out_dir)
            result = importer.import_csv(csv_path)

        assert result.unmapped == 1
        assert result.cost_upserted == 0
        assert (out_dir / "unmapped_asins.csv").exists()

    def test_isbn_non_amazon(self, in_memory_db: Session, tmp_path: Path):
        """ISBN（10 位数字）→ non_amazon_costs.csv。"""
        csv_path = make_amazon_csv(tmp_path / "test.csv", [
            {"asin": "4499228646", "qty": 1, "amount": 1980, "title": "Book ISBN"},
        ])

        out_dir = tmp_path / "out"
        with patch("modules.finance.amazon_cost_importer.get_session") as mock_sess:
            mock_sess.return_value.__enter__ = MagicMock(return_value=in_memory_db)
            mock_sess.return_value.__exit__ = MagicMock(return_value=False)
            importer = AmazonCostImporter(output_dir=out_dir)
            result = importer.import_csv(csv_path)

        assert result.non_amazon == 1
        assert result.cost_upserted == 0
        assert (out_dir / "non_amazon_costs.csv").exists()

    def test_zero_qty_rows_skipped(self, in_memory_db: Session, tmp_path: Path):
        """qty=0 行（退货）→ 跳过，不进任何路由。"""
        # 先建有 ASIN 的 Product（让 valid 行能入库）
        in_memory_db.add(Product(
            sku="SKU-VALID01",
            title=None,
            asin="B0VALID001",
            source_url="https://www.amazon.co.jp/dp/B0VALID001",
            cost_price=None,
            cost_currency="JPY",
            status=ProductStatus.ACTIVE,
        ))
        in_memory_db.commit()

        csv_path = make_amazon_csv(tmp_path / "test.csv", [
            {"asin": "B0ZEROTES2", "qty": 0, "amount": 0, "title": "Zero Qty"},
            {"asin": "B0VALID001", "qty": 1, "amount": 1000, "title": "Valid"},
        ])

        with patch("modules.finance.amazon_cost_importer.get_session") as mock_sess:
            mock_sess.return_value.__enter__ = MagicMock(return_value=in_memory_db)
            mock_sess.return_value.__exit__ = MagicMock(return_value=False)
            importer = AmazonCostImporter(output_dir=tmp_path / "out")
            result = importer.import_csv(csv_path)

        assert result.rows_zero_qty == 1
        assert result.cost_upserted == 1   # 有效行仍入库

    def test_weighted_average_multi_row(self, in_memory_db: Session, tmp_path: Path):
        """同 ASIN 多笔进货 → 加权平均（Σamount / Σqty）。"""
        in_memory_db.add(Product(
            sku="SKU-WEIGHT",
            title=None,
            asin="B0WEIGHT01",
            source_url="https://www.amazon.co.jp/dp/B0WEIGHT01",
            cost_price=None,
            cost_currency="JPY",
            status=ProductStatus.ACTIVE,
        ))
        in_memory_db.commit()

        # 两笔: 1000円×2个 + 1500円×1个 = 3500/3 = 1166.67
        csv_path = make_amazon_csv(tmp_path / "test.csv", [
            {"asin": "B0WEIGHT01", "qty": 2, "amount": 2000, "title": "Weight 1"},
            {"asin": "B0WEIGHT01", "qty": 1, "amount": 1500, "title": "Weight 2"},
        ])

        with patch("modules.finance.amazon_cost_importer.get_session") as mock_sess:
            mock_sess.return_value.__enter__ = MagicMock(return_value=in_memory_db)
            mock_sess.return_value.__exit__ = MagicMock(return_value=False)
            importer = AmazonCostImporter(output_dir=tmp_path / "out")
            result = importer.import_csv(csv_path)

        assert result.cost_upserted == 1
        p = in_memory_db.get(Product, "SKU-WEIGHT")
        assert p.cost_price == Decimal("1166.67")   # (2000+1500)/3 quantized

    def test_missing_asin_column_raises(self, in_memory_db: Session, tmp_path: Path):
        """CSV 缺少 ASIN 列 → 抛友好 RuntimeError。"""
        # 写入一个没有 ASIN 列的 CSV
        bad_path = tmp_path / "bad.csv"
        with open(bad_path, "w", newline="", encoding="utf-8") as f:
            f.write("注文日,qty\n2026/04/01,1\n")

        with pytest.raises(RuntimeError, match="缺少必要列"):
            AmazonCostImporter(output_dir=tmp_path / "out").import_csv(bad_path)

    def test_output_dir_auto_created(self, in_memory_db: Session, tmp_path: Path):
        """输出目录不存在 → 自动创建。"""
        in_memory_db.add(Product(
            sku="SKU-DIR01",
            title=None,
            asin="B0DIRTEST01",
            source_url="https://www.amazon.co.jp/dp/B0DIRTEST01",
            cost_price=None,
            cost_currency="JPY",
            status=ProductStatus.ACTIVE,
        ))
        in_memory_db.commit()

        csv_path = make_amazon_csv(tmp_path / "test.csv", [
            {"asin": "B0DIRTEST01", "qty": 1, "amount": 1000, "title": "Dir Test"},
        ])

        new_dir = tmp_path / "nested" / "deep" / "imports"
        assert not new_dir.exists()

        with patch("modules.finance.amazon_cost_importer.get_session") as mock_sess:
            mock_sess.return_value.__enter__ = MagicMock(return_value=in_memory_db)
            mock_sess.return_value.__exit__ = MagicMock(return_value=False)
            importer = AmazonCostImporter(output_dir=new_dir)
            result = importer.import_csv(csv_path)

        assert new_dir.exists()
        assert (new_dir / "import_summary.txt").exists()

    def test_amount_dimension_balances(self, in_memory_db: Session, tmp_path: Path):
        """金额维度：total == upserted + ambiguous + unmapped + non_amazon。"""
        in_memory_db.add(Product(
            sku="SKU-AMB",
            title=None,
            asin="B0AMBCHECK",
            source_url="https://www.amazon.co.jp/dp/B0AMBCHECK",
            cost_price=None,
            cost_currency="JPY",
            status=ProductStatus.ACTIVE,
        ))
        in_memory_db.add(Product(
            sku="SKU-AMB2",
            title=None,
            asin="B0AMBCHECK",
            source_url="https://www.amazon.co.jp/dp/B0AMBCHECK",
            cost_price=None,
            cost_currency="JPY",
            status=ProductStatus.ACTIVE,
        ))
        in_memory_db.commit()

        csv_path = make_amazon_csv(tmp_path / "test.csv", [
            # upserted (unique ASIN)
            {"asin": "B0UPSERT01", "qty": 1, "amount": 5000, "title": "Up"},
            # ambiguous (shared ASIN with two SKUs, each 3000)
            {"asin": "B0AMBCHECK", "qty": 2, "amount": 6000, "title": "Amb"},
            # unmapped (no product)
            {"asin": "B0UNMAPPED", "qty": 1, "amount": 2000, "title": "Unmap"},
            # non-amazon (ISBN)
            {"asin": "1234567890", "qty": 1, "amount": 1000, "title": "ISBN"},
        ])

        with patch("modules.finance.amazon_cost_importer.get_session") as mock_sess:
            mock_sess.return_value.__enter__ = MagicMock(return_value=in_memory_db)
            mock_sess.return_value.__exit__ = MagicMock(return_value=False)
            importer = AmazonCostImporter(output_dir=tmp_path / "out")
            result = importer.import_csv(csv_path)

        total = result.total_amount_jpy
        parts = (
            result.upserted_amount_jpy
            + result.ambiguous_amount_jpy
            + result.unmapped_amount_jpy
            + result.non_amazon_amount_jpy
        )
        assert total == parts, f"{total} != {parts}"

    def test_supplier_field_set_to_amazon_jp(self, in_memory_db: Session, tmp_path: Path):
        """upsert 后 supplier 字段 = 'Amazon JP'。"""
        in_memory_db.add(Product(
            sku="SKU-SUPPLIER",
            title=None,
            asin="B0SUPPLIER",
            source_url="https://www.amazon.co.jp/dp/B0SUPPLIER",
            cost_price=None,
            cost_currency="JPY",
            status=ProductStatus.ACTIVE,
        ))
        in_memory_db.commit()

        csv_path = make_amazon_csv(tmp_path / "test.csv", [
            {"asin": "B0SUPPLIER", "qty": 1, "amount": 1000, "title": "Supplier Test"},
        ])

        with patch("modules.finance.amazon_cost_importer.get_session") as mock_sess:
            mock_sess.return_value.__enter__ = MagicMock(return_value=in_memory_db)
            mock_sess.return_value.__exit__ = MagicMock(return_value=False)
            importer = AmazonCostImporter(output_dir=tmp_path / "out")
            importer.import_csv(csv_path)

        p = in_memory_db.get(Product, "SKU-SUPPLIER")
        assert p.supplier == "Amazon JP"

    def test_cost_currency_set_to_jpy(self, in_memory_db: Session, tmp_path: Path):
        """upsert 后 cost_currency = 'JPY'。"""
        in_memory_db.add(Product(
            sku="SKU-CURR",
            title=None,
            asin="B0CURRTEST",
            source_url="https://www.amazon.co.jp/dp/B0CURRTEST",
            cost_price=None,
            cost_currency="USD",   # 旧值
            status=ProductStatus.ACTIVE,
        ))
        in_memory_db.commit()

        csv_path = make_amazon_csv(tmp_path / "test.csv", [
            {"asin": "B0CURRTEST", "qty": 1, "amount": 1000, "title": "Currency Test"},
        ])

        with patch("modules.finance.amazon_cost_importer.get_session") as mock_sess:
            mock_sess.return_value.__enter__ = MagicMock(return_value=in_memory_db)
            mock_sess.return_value.__exit__ = MagicMock(return_value=False)
            importer = AmazonCostImporter(output_dir=tmp_path / "out")
            importer.import_csv(csv_path)

        p = in_memory_db.get(Product, "SKU-CURR")
        assert p.cost_currency == "JPY"
