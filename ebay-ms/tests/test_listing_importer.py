"""
tests/test_listing_importer.py
ListingImporter 单元测试（Brief 1, Step 4）
"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

import openpyxl
import pytest
from core.models import Product, ProductStatus
from core.models.base import Base
from modules.listing.listing_importer import ListingImporter
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def in_memory_db(tmp_path: Path) -> Session:
    """独立的内存 SQLite 数据库，隔离测试。"""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as sess:
        yield sess


def make_minimal_excel(path: Path, rows: list[dict]) -> Path:
    """生成最简 Excel，匹配 Ariel 真实 v2/v3 Excel 的 row 结构。

    真实结构:
      row 1: 汇率参考行（混合内容，pandas 当数据忽略）
      row 2: 空行
      row 3: 字段名（表头）
      row 4: 例子（被 DROP_FIRST_DATA_ROW 剔除）
      row 5+: 真实数据

    ListingImporter 用 header=2（0-indexed=row 3 的 0-indexed=2）。
    """
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "利润试算表"
    ws.append(["汇率", 142.0])                   # row 1: 杂项行
    ws.append([None, None])                       # row 2: 空行
    ws.append(["EC site URL", "ItemID（SKU)"])    # row 3: 字段名（表头）
    ws.append(["例子", "示例"])                  # row 4: 例子（DROP）
    for r in rows:
        ws.append([r.get("url", ""), r.get("sku", "")])
    wb.save(str(path))
    return path


# ── ListingImporter 主类测试 ──────────────────────────────────────────────────

class TestListingImporter:
    """核心 upsert 逻辑测试。"""

    def test_insert_new_skus(self, in_memory_db: Session, tmp_path: Path):
        """1-to-1 映射 → 全部新建 SKU。"""
        xlsx = tmp_path / "test_v3.xlsx"
        make_minimal_excel(xlsx, [
            {"sku": "SKU-001", "url": "https://www.amazon.co.jp/dp/B0ABCDEF12"},
            {"sku": "SKU-002", "url": "https://www.amazon.co.jp/dp/B0ABCDEF34"},
        ])

        with patch("modules.listing.listing_importer.get_session") as mock_sess:
            mock_sess.return_value.__enter__ = MagicMock(return_value=in_memory_db)
            mock_sess.return_value.__exit__ = MagicMock(return_value=False)
            importer = ListingImporter(expand_short_links=False)
            result = importer.import_files([xlsx])

        assert result.sku_inserted == 2
        assert result.sku_updated == 0
        assert result.sku_unchanged == 0
        assert result.rows_no_sku == 0
        assert result.rows_no_url == 0

        # 验证 asin 抽取正确
        p1 = in_memory_db.get(Product, "SKU-001")
        assert p1 is not None
        assert p1.asin == "B0ABCDEF12"
        assert p1.status == ProductStatus.ACTIVE
        assert p1.title is None
        assert p1.cost_price is None

    def test_v3_priority_skips_v2_duplicate(self, in_memory_db: Session, tmp_path: Path):
        """v3 在命令行前面 → v3 的值优先（先遇到先写入）。"""
        v3 = tmp_path / "v3.xlsx"
        make_minimal_excel(v3, [
            {"sku": "SKU-001", "url": "https://www.amazon.co.jp/dp/B0BBB22222"},
        ])
        v2 = tmp_path / "v2.xlsx"
        make_minimal_excel(v2, [
            {"sku": "SKU-001", "url": "https://www.amazon.co.jp/dp/B0AAA11111"},
        ])

        with patch("modules.listing.listing_importer.get_session") as mock_sess:
            mock_sess.return_value.__enter__ = MagicMock(return_value=in_memory_db)
            mock_sess.return_value.__exit__ = MagicMock(return_value=False)
            importer = ListingImporter(expand_short_links=False)
            # v3 在前，v2 在后 → v3 先写入，v2 被跳过
            result = importer.import_files([v3, v2])

        assert result.sku_inserted == 1
        p = in_memory_db.get(Product, "SKU-001")
        assert p.asin == "B0BBB22222"   # v3 的值优先

    def test_no_url_skus_still_inserted(self, in_memory_db: Session, tmp_path: Path):
        """无 URL 的行仍预建 SKU（asin=NULL），只记 rows_no_url。"""
        xlsx = tmp_path / "no_url.xlsx"
        make_minimal_excel(xlsx, [
            {"sku": "SKU-NO-URL", "url": ""},
        ])

        with patch("modules.listing.listing_importer.get_session") as mock_sess:
            mock_sess.return_value.__enter__ = MagicMock(return_value=in_memory_db)
            mock_sess.return_value.__exit__ = MagicMock(return_value=False)
            importer = ListingImporter(expand_short_links=False)
            result = importer.import_files([xlsx])

        assert result.sku_inserted == 1
        assert result.rows_no_url == 1   # 空 URL 计数（但仍预建）
        p = in_memory_db.get(Product, "SKU-NO-URL")
        assert p is not None
        assert p.asin is None
        assert p.source_url is None

    def test_existing_sku_no_change_skipped(self, in_memory_db: Session, tmp_path: Path):
        """已存在的 SKU 无变化 → 跳过（unchanged 计数）。"""
        # 先插入一条
        in_memory_db.add(Product(
            sku="EXISTING-SKU",
            title=None,
            asin="B0CCCC3333",
            source_url="https://www.amazon.co.jp/dp/B0CCCC3333",
            cost_price=None,
            cost_currency="JPY",
            status=ProductStatus.ACTIVE,
        ))
        in_memory_db.commit()

        xlsx = tmp_path / "unchanged.xlsx"
        make_minimal_excel(xlsx, [
            {"sku": "EXISTING-SKU", "url": "https://www.amazon.co.jp/dp/B0CCCC3333"},
        ])

        with patch("modules.listing.listing_importer.get_session") as mock_sess:
            mock_sess.return_value.__enter__ = MagicMock(return_value=in_memory_db)
            mock_sess.return_value.__exit__ = MagicMock(return_value=False)
            importer = ListingImporter(expand_short_links=False)
            result = importer.import_files([xlsx])

        assert result.sku_inserted == 0
        assert result.sku_updated == 0
        assert result.sku_unchanged == 1

    def test_existing_sku_with_url_change_updates(self, in_memory_db: Session, tmp_path: Path):
        """已存在 SKU 但 URL/ASIN 变化 → UPDATE。"""
        in_memory_db.add(Product(
            sku="OLD-SKU",
            title=None,
            asin="B0OLD44444",
            source_url="https://www.amazon.co.jp/dp/B0OLD44444",
            cost_price=None,
            cost_currency="JPY",
            status=ProductStatus.ACTIVE,
        ))
        in_memory_db.commit()

        xlsx = tmp_path / "update.xlsx"
        make_minimal_excel(xlsx, [
            {"sku": "OLD-SKU", "url": "https://www.amazon.co.jp/dp/B0NEW55555"},
        ])

        with patch("modules.listing.listing_importer.get_session") as mock_sess:
            mock_sess.return_value.__enter__ = MagicMock(return_value=in_memory_db)
            mock_sess.return_value.__exit__ = MagicMock(return_value=False)
            importer = ListingImporter(expand_short_links=False)
            result = importer.import_files([xlsx])

        assert result.sku_updated == 1
        p = in_memory_db.get(Product, "OLD-SKU")
        assert p.asin == "B0NEW55555"

    def test_dup_in_same_file_counted(self, in_memory_db: Session, tmp_path: Path):
        """同一文件内重复 SKU → 计入 rows_dup_in_source。"""
        xlsx = tmp_path / "dup.xlsx"
        make_minimal_excel(xlsx, [
            {"sku": "SKU-DUP", "url": "https://www.amazon.co.jp/dp/B0AAAA1111"},
            {"sku": "SKU-DUP", "url": "https://www.amazon.co.jp/dp/B0BBBB2222"},
        ])

        with patch("modules.listing.listing_importer.get_session") as mock_sess:
            mock_sess.return_value.__enter__ = MagicMock(return_value=in_memory_db)
            mock_sess.return_value.__exit__ = MagicMock(return_value=False)
            importer = ListingImporter(expand_short_links=False)
            result = importer.import_files([xlsx])

        assert result.rows_dup_in_source == 1
        assert "SKU-DUP" in result.duplicate_skus

    def test_row_without_sku_skipped(self, in_memory_db: Session, tmp_path: Path):
        """无 SKU 行 → 跳过，不入库，计入 rows_no_sku。"""
        xlsx = tmp_path / "no_sku.xlsx"
        make_minimal_excel(xlsx, [
            {"sku": "", "url": "https://www.amazon.co.jp/dp/B0ABCDEF12"},
        ])

        with patch("modules.listing.listing_importer.get_session") as mock_sess:
            mock_sess.return_value.__enter__ = MagicMock(return_value=in_memory_db)
            mock_sess.return_value.__exit__ = MagicMock(return_value=False)
            importer = ListingImporter(expand_short_links=False)
            result = importer.import_files([xlsx])

        assert result.rows_no_sku == 1
        assert result.sku_inserted == 0

    def test_short_link_expanded_writes_full_url(
        self, in_memory_db: Session, tmp_path: Path
    ):
        """短链展开 ON → asin 来自展开后 URL + source_url 覆写为完整 URL。"""
        xlsx = tmp_path / "short_link.xlsx"
        make_minimal_excel(xlsx, [
            {"sku": "SKU-SHORT", "url": "https://amzn.asia/XYZ123"},
        ])

        def mock_head(url, **kw):
            r = Mock(spec=["status_code", "headers"])
            r.status_code = 302
            r.headers = {"location": "https://www.amazon.co.jp/dp/B0ABCDEF12"}
            return r

        def mock_get(url, **kw):
            r = Mock(spec=["url"])
            r.url = "https://www.amazon.co.jp/dp/B0ABCDEF12"
            return r

        with patch("modules.listing.listing_importer.get_session") as mock_sess, \
             patch("httpx.Client") as mock_client_cls:
            mock_sess.return_value.__enter__ = MagicMock(return_value=in_memory_db)
            mock_sess.return_value.__exit__ = MagicMock(return_value=False)
            mock_client = MagicMock()
            mock_client.head = Mock(side_effect=mock_head)
            mock_client.get = Mock(side_effect=mock_get)
            mock_client.__enter__ = Mock(return_value=mock_client)
            mock_client.__exit__ = Mock(return_value=False)
            mock_client_cls.return_value = mock_client
            importer = ListingImporter(expand_short_links=True)
            result = importer.import_files([xlsx])

        assert result.sku_inserted == 1
        assert result.short_links_expanded == 1
        p = in_memory_db.get(Product, "SKU-SHORT")
        assert p.asin == "B0ABCDEF12"   # ASIN 抽出自展开后 URL
        assert "amazon.co.jp" in p.source_url   # source_url 覆写为完整 URL

    def test_non_amazon_url_no_asin_but_inserted(
        self, in_memory_db: Session, tmp_path: Path
    ):
        """Yahoo / Muji / 1101 等非 Amazon URL → asin=NULL 但 SKU 仍预建。"""
        xlsx = tmp_path / "non_amazon.xlsx"
        make_minimal_excel(xlsx, [
            {"sku": "SKU-YAHOO", "url": "https://paypay.auctions.example.com/item/123"},
            {"sku": "SKU-MUJI", "url": "https://muji.com/products/456"},
        ])

        with patch("modules.listing.listing_importer.get_session") as mock_sess:
            mock_sess.return_value.__enter__ = MagicMock(return_value=in_memory_db)
            mock_sess.return_value.__exit__ = MagicMock(return_value=False)
            importer = ListingImporter(expand_short_links=False)
            result = importer.import_files([xlsx])

        assert result.sku_inserted == 2
        p_yahoo = in_memory_db.get(Product, "SKU-YAHOO")
        assert p_yahoo.asin is None
        assert p_yahoo.source_url == "https://paypay.auctions.example.com/item/123"
        p_muji = in_memory_db.get(Product, "SKU-MUJI")
        assert p_muji.asin is None
        assert p_muji.source_url == "https://muji.com/products/456"

    def test_existing_sku_not_in_listing_remains_in_db(
        self, in_memory_db: Session, tmp_path: Path
    ):
        """已有 Product 但 listing 表里 SKU 不再出现 → DB 仍保留。"""
        in_memory_db.add(Product(
            sku="OLD-ONLY-SKU",
            title=None,
            asin="B0OLDONLY1",
            source_url="https://www.amazon.co.jp/dp/B0OLDONLY1",
            cost_price=None,
            cost_currency="JPY",
            status=ProductStatus.ACTIVE,
        ))
        in_memory_db.commit()
        old_count = in_memory_db.query(Product).count()   # 1

        xlsx = tmp_path / "new_only.xlsx"
        make_minimal_excel(xlsx, [
            {"sku": "NEW-SKU", "url": "https://www.amazon.co.jp/dp/B0NEWONLY2"},
        ])

        with patch("modules.listing.listing_importer.get_session") as mock_sess:
            mock_sess.return_value.__enter__ = MagicMock(return_value=in_memory_db)
            mock_sess.return_value.__exit__ = MagicMock(return_value=False)
            importer = ListingImporter(expand_short_links=False)
            result = importer.import_files([xlsx])

        assert result.sku_inserted == 1
        # 旧 SKU 仍在 DB 中
        assert in_memory_db.query(Product).count() == old_count + 1
        p_old = in_memory_db.get(Product, "OLD-ONLY-SKU")
        assert p_old is not None


# ── ASIN 工具函数测试 ──────────────────────────────────────────────────────────

class TestAsinUtils:
    """core/utils/asin.py 工具函数测试。"""

    def test_extract_asin_standard_dp(self):
        from core.utils.asin import extract_asin_from_url
        assert extract_asin_from_url("https://www.amazon.co.jp/dp/B0ABCDEF12") == "B0ABCDEF12"
        assert extract_asin_from_url("https://www.amazon.com/dp/B0XYZ12345") == "B0XYZ12345"

    def test_extract_asin_gp_product(self):
        from core.utils.asin import extract_asin_from_url
        assert extract_asin_from_url("https://www.amazon.co.jp/gp/product/B0ABCDEF12") == "B0ABCDEF12"

    def test_extract_asin_gp_aw_d(self):
        from core.utils.asin import extract_asin_from_url
        assert extract_asin_from_url("https://www.amazon.co.jp/gp/aw/d/B0ABCDEF12") == "B0ABCDEF12"

    def test_extract_asin_short_link_not_expanded(self):
        """extract 不展开短链，只匹配标准 URL。"""
        from core.utils.asin import extract_asin_from_url
        assert extract_asin_from_url("https://amzn.asia/abc123") is None

    def test_extract_asin_invalid(self):
        from core.utils.asin import extract_asin_from_url
        assert extract_asin_from_url("https://www.amazon.co.jp/dp/JUNK") is None
        assert extract_asin_from_url(None) is None
        assert extract_asin_from_url("") is None

    def test_is_short_link(self):
        from core.utils.asin import is_short_link
        assert is_short_link("https://amzn.asia/abc123") is True
        assert is_short_link("https://www.amazon.co.jp/dp/B0ABCDEF12") is False
        assert is_short_link(None) is False

    def test_is_standard_asin(self):
        from core.utils.asin import is_standard_asin
        assert is_standard_asin("B0ABCDEF12") is True
        assert is_standard_asin("B0ABCDEF1") is False     # 9 位
        assert is_standard_asin("X0ABCDEF12") is False    # 非 B0 开头
        assert is_standard_asin("1234567890") is False    # ISBN 风格
        assert is_standard_asin(None) is False

    def test_clean_amazon_csv_asin(self):
        from core.utils.asin import clean_amazon_csv_asin
        assert clean_amazon_csv_asin('="B0ABCDEF12"') == "B0ABCDEF12"
        assert clean_amazon_csv_asin('="B0XYZ12345"') == "B0XYZ12345"
        assert clean_amazon_csv_asin("B0ABCDEF12") == "B0ABCDEF12"
        assert clean_amazon_csv_asin(None) is None
