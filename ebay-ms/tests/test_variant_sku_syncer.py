"""
tests/test_variant_sku_syncer.py
VariantSkuSyncer 单元测试（Brief 3 T5）

数据源：order_items（含下划线的子 SKU）
"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from core.models import OrderItem, Product, ProductStatus
from core.models.base import Base
from modules.listing.variant_sku_syncer import (
    VariantSkuSyncer,
    _build_variant_note,
    _parent_sku_from_child,
    _suffix_from_sku,
)
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


# ── Helper 函数测试 ───────────────────────────────────────────────────────────

class TestHelperFunctions:
    def test_parent_sku_from_child_simple(self):
        # 真实数据样例：下划线分隔
        assert _parent_sku_from_child("01-2509-0002_Da") == "01-2509-0002"
        assert _parent_sku_from_child("01-2509-0002_Wh") == "01-2509-0002"
        assert _parent_sku_from_child("01-2509-0002_Em") == "01-2509-0002"
        assert _parent_sku_from_child("SAME") == "SAME"  # 无下划线 → 原样返回

    def test_suffix_from_sku(self):
        assert _suffix_from_sku("01-2509-0002_Da") == "Da"
        assert _suffix_from_sku("ABC-001_SET") == "SET"
        assert _suffix_from_sku("SAME") == ""

    def test_variant_note_preserves_raw_suffix(self):
        """variant_note = Suffix: {raw_suffix}，不做语义翻译。"""
        assert _build_variant_note("Da") == "Suffix: Da"
        assert _build_variant_note("Wh") == "Suffix: Wh"
        assert _build_variant_note("RED") == "Suffix: RED"
        assert _build_variant_note("M") == "Suffix: M"
        assert _build_variant_note("SET") == "Suffix: SET"
        assert _build_variant_note("XYZ") == "Suffix: XYZ"
        assert _build_variant_note("CUSTOM") == "Suffix: CUSTOM"
        assert _build_variant_note("#04") == "Suffix: #04"
        assert _build_variant_note("bl") == "Suffix: bl"

    def test_double_underscore_uses_last_segment_as_variant(self):
        """双下划线：rsplit("_", 1) 只切最后一个下划线。"""
        assert _parent_sku_from_child("01-2509-0002_Da_v2") == "01-2509-0002_Da"
        assert _suffix_from_sku("01-2509-0002_Da_v2") == "v2"
        assert _build_variant_note("v2") == "Suffix: v2"

        assert _parent_sku_from_child("A_B_C") == "A_B"
        assert _suffix_from_sku("A_B_C") == "C"


# ── VariantSkuSyncer 主类测试 ─────────────────────────────────────────────────

class TestVariantSkuSyncer:
    def test_create_new_child_sku(self, in_memory_db: Session, tmp_path: Path):
        """子 SKU 不存在 → 创建，parent_sku 正确。"""
        in_memory_db.add(Product(
            sku="01-2509-0002",
            title=None,
            asin=None,
            source_url=None,
            cost_price=None,
            cost_currency="JPY",
            status=ProductStatus.ACTIVE,
        ))
        in_memory_db.add(OrderItem(
            order_id="ORDER-001",
            sku="01-2509-0002_Da",
            quantity=1,
            unit_price=1000.0,
            sale_amount=1000.0,
        ))
        in_memory_db.commit()

        with patch("modules.listing.variant_sku_syncer.get_session") as mock_sess:
            mock_sess.return_value.__enter__ = MagicMock(return_value=in_memory_db)
            mock_sess.return_value.__exit__ = MagicMock(return_value=False)
            syncer = VariantSkuSyncer()
            result = syncer.sync_from_order_items()

        assert result.created == 1
        assert result.skipped == 0
        p = in_memory_db.get(Product, "01-2509-0002_Da")
        assert p is not None
        assert p.parent_sku == "01-2509-0002"
        assert p.variant_note == "Suffix: Da"
        assert p.status == ProductStatus.ACTIVE

    def test_idempotent_rerun(self, in_memory_db: Session, tmp_path: Path):
        """同输入跑两次：第二次全部 update，DB 状态一致。"""
        in_memory_db.add(Product(
            sku="PARENT-001",
            title=None,
            asin=None,
            source_url=None,
            cost_price=None,
            cost_currency="JPY",
            status=ProductStatus.ACTIVE,
        ))
        in_memory_db.add(OrderItem(
            order_id="ORDER-001",
            sku="PARENT-001_Wh",
            quantity=1,
            unit_price=500.0,
            sale_amount=500.0,
        ))
        in_memory_db.commit()

        with patch("modules.listing.variant_sku_syncer.get_session") as mock_sess:
            mock_sess.return_value.__enter__ = MagicMock(return_value=in_memory_db)
            mock_sess.return_value.__exit__ = MagicMock(return_value=False)
            syncer = VariantSkuSyncer()
            r1 = syncer.sync_from_order_items()

        assert r1.created == 1
        assert r1.updated == 0

        with patch("modules.listing.variant_sku_syncer.get_session") as mock_sess:
            mock_sess.return_value.__enter__ = MagicMock(return_value=in_memory_db)
            mock_sess.return_value.__exit__ = MagicMock(return_value=False)
            syncer = VariantSkuSyncer()
            r2 = syncer.sync_from_order_items()

        assert r2.created == 0
        assert r2.updated == 1

    def test_skip_when_parent_missing(self, in_memory_db: Session, tmp_path: Path):
        """父 SKU 不在 products 表 → 跳过 + skipped_detail 有记录。"""
        in_memory_db.add(OrderItem(
            order_id="ORDER-001",
            sku="NO-PARENT_Da",
            quantity=1,
            unit_price=500.0,
            sale_amount=500.0,
        ))
        in_memory_db.commit()

        out_dir = tmp_path / "out"
        with patch("modules.listing.variant_sku_syncer.get_session") as mock_sess:
            mock_sess.return_value.__enter__ = MagicMock(return_value=in_memory_db)
            mock_sess.return_value.__exit__ = MagicMock(return_value=False)
            syncer = VariantSkuSyncer()
            syncer.OUTPUT_DIR = out_dir
            result = syncer.sync_from_order_items()

        assert result.skipped == 1
        assert result.created == 0
        assert result.skipped_detail[0]["sku"] == "NO-PARENT_Da"

    def test_skip_when_collision_with_existing_parent(self, in_memory_db: Session, tmp_path: Path):
        """子 SKU 字符串撞已存在父 SKU → 走 update 路径（幂等）。"""
        in_memory_db.add(Product(
            sku="PARENT-A",
            title=None,
            asin=None,
            source_url=None,
            cost_price=None,
            cost_currency="JPY",
            status=ProductStatus.ACTIVE,
        ))
        in_memory_db.add(Product(
            sku="PARENT-A_Da",
            title=None,
            asin=None,
            source_url=None,
            cost_price=None,
            cost_currency="JPY",
            status=ProductStatus.ACTIVE,
        ))
        in_memory_db.add(OrderItem(
            order_id="ORDER-001",
            sku="PARENT-A_Da",
            quantity=1,
            unit_price=500.0,
            sale_amount=500.0,
        ))
        in_memory_db.commit()

        with patch("modules.listing.variant_sku_syncer.get_session") as mock_sess:
            mock_sess.return_value.__enter__ = MagicMock(return_value=in_memory_db)
            mock_sess.return_value.__exit__ = MagicMock(return_value=False)
            syncer = VariantSkuSyncer()
            result = syncer.sync_from_order_items()

        assert result.updated == 1
        assert result.skipped == 0

    def test_variant_note_preserves_raw_suffix(self, in_memory_db: Session, tmp_path: Path):
        """新建子 SKU variant_note = Suffix: {raw_suffix}。"""
        in_memory_db.add(Product(
            sku="NOTE-PARENT",
            title=None,
            asin=None,
            source_url=None,
            cost_price=None,
            cost_currency="JPY",
            status=ProductStatus.ACTIVE,
        ))
        in_memory_db.add(OrderItem(
            order_id="ORDER-001",
            sku="NOTE-PARENT_Da",
            quantity=1,
            unit_price=500.0,
            sale_amount=500.0,
        ))
        in_memory_db.commit()

        with patch("modules.listing.variant_sku_syncer.get_session") as mock_sess:
            mock_sess.return_value.__enter__ = MagicMock(return_value=in_memory_db)
            mock_sess.return_value.__exit__ = MagicMock(return_value=False)
            syncer = VariantSkuSyncer()
            syncer.sync_from_order_items()

        p = in_memory_db.get(Product, "NOTE-PARENT_Da")
        assert p.variant_note == "Suffix: Da"

    def test_variant_note_empty_when_no_aspects(self, in_memory_db: Session, tmp_path: Path):
        """无下划线的 SKU → 不被 syncer 处理。"""
        in_memory_db.add(Product(
            sku="SIMPLE-PARENT",
            title=None,
            asin=None,
            source_url=None,
            cost_price=None,
            cost_currency="JPY",
            status=ProductStatus.ACTIVE,
        ))
        in_memory_db.add(OrderItem(
            order_id="ORDER-001",
            sku="SIMPLE-PARENT",
            quantity=1,
            unit_price=500.0,
            sale_amount=500.0,
        ))
        in_memory_db.commit()

        with patch("modules.listing.variant_sku_syncer.get_session") as mock_sess:
            mock_sess.return_value.__enter__ = MagicMock(return_value=in_memory_db)
            mock_sess.return_value.__exit__ = MagicMock(return_value=False)
            syncer = VariantSkuSyncer()
            result = syncer.sync_from_order_items()

        assert result.child_skus_found == 0
        assert result.created == 0

    def test_cost_price_remains_null(self, in_memory_db: Session, tmp_path: Path):
        """新建子 SKU cost_price 是 NULL（不继承父）。"""
        in_memory_db.add(Product(
            sku="COST-PARENT",
            title=None,
            asin=None,
            source_url=None,
            cost_price=1000.0,
            cost_currency="JPY",
            status=ProductStatus.ACTIVE,
        ))
        in_memory_db.add(OrderItem(
            order_id="ORDER-001",
            sku="COST-PARENT_Da",
            quantity=1,
            unit_price=500.0,
            sale_amount=500.0,
        ))
        in_memory_db.commit()

        with patch("modules.listing.variant_sku_syncer.get_session") as mock_sess:
            mock_sess.return_value.__enter__ = MagicMock(return_value=in_memory_db)
            mock_sess.return_value.__exit__ = MagicMock(return_value=False)
            syncer = VariantSkuSyncer()
            syncer.sync_from_order_items()

        p = in_memory_db.get(Product, "COST-PARENT_Da")
        assert p.cost_price is None

    def test_asin_remains_null(self, in_memory_db: Session, tmp_path: Path):
        """新建子 SKU asin 是 NULL。"""
        in_memory_db.add(Product(
            sku="ASIN-PARENT",
            title=None,
            asin="B0ASINPARENT",
            source_url=None,
            cost_price=None,
            cost_currency="JPY",
            status=ProductStatus.ACTIVE,
        ))
        in_memory_db.add(OrderItem(
            order_id="ORDER-001",
            sku="ASIN-PARENT_Da",
            quantity=1,
            unit_price=500.0,
            sale_amount=500.0,
        ))
        in_memory_db.commit()

        with patch("modules.listing.variant_sku_syncer.get_session") as mock_sess:
            mock_sess.return_value.__enter__ = MagicMock(return_value=in_memory_db)
            mock_sess.return_value.__exit__ = MagicMock(return_value=False)
            syncer = VariantSkuSyncer()
            syncer.sync_from_order_items()

        p = in_memory_db.get(Product, "ASIN-PARENT_Da")
        assert p.asin is None

    def test_status_defaults_to_active(self, in_memory_db: Session, tmp_path: Path):
        """新建子 SKU status = 'active'。"""
        in_memory_db.add(Product(
            sku="STATUS-PARENT",
            title=None,
            asin=None,
            source_url=None,
            cost_price=None,
            cost_currency="JPY",
            status=ProductStatus.ACTIVE,
        ))
        in_memory_db.add(OrderItem(
            order_id="ORDER-001",
            sku="STATUS-PARENT_Da",
            quantity=1,
            unit_price=500.0,
            sale_amount=500.0,
        ))
        in_memory_db.commit()

        with patch("modules.listing.variant_sku_syncer.get_session") as mock_sess:
            mock_sess.return_value.__enter__ = MagicMock(return_value=in_memory_db)
            mock_sess.return_value.__exit__ = MagicMock(return_value=False)
            syncer = VariantSkuSyncer()
            syncer.sync_from_order_items()

        p = in_memory_db.get(Product, "STATUS-PARENT_Da")
        assert p.status == ProductStatus.ACTIVE

    def test_dry_run_does_not_write_db(self, in_memory_db: Session, tmp_path: Path):
        """--dry-run 跑完 DB 无变化。"""
        in_memory_db.add(Product(
            sku="DRY-PARENT",
            title=None,
            asin=None,
            source_url=None,
            cost_price=None,
            cost_currency="JPY",
            status=ProductStatus.ACTIVE,
        ))
        in_memory_db.add(OrderItem(
            order_id="ORDER-001",
            sku="DRY-PARENT_Da",
            quantity=1,
            unit_price=500.0,
            sale_amount=500.0,
        ))
        in_memory_db.commit()

        with patch("modules.listing.variant_sku_syncer.get_session") as mock_sess:
            mock_sess.return_value.__enter__ = MagicMock(return_value=in_memory_db)
            mock_sess.return_value.__exit__ = MagicMock(return_value=False)
            syncer = VariantSkuSyncer()
            result = syncer.sync_from_order_items(dry_run=True)

        assert result.created == 0
        assert result.updated == 0
        assert in_memory_db.get(Product, "DRY-PARENT_Da") is None

    def test_empty_order_items(self, in_memory_db: Session, tmp_path: Path):
        """order_items 全空 → SyncResult: 0/0/0/0，不报错。"""
        with patch("modules.listing.variant_sku_syncer.get_session") as mock_sess:
            mock_sess.return_value.__enter__ = MagicMock(return_value=in_memory_db)
            mock_sess.return_value.__exit__ = MagicMock(return_value=False)
            syncer = VariantSkuSyncer()
            result = syncer.sync_from_order_items()

        assert result.child_skus_found == 0
        assert result.created == 0
        assert result.updated == 0
        assert result.skipped == 0
        assert result.errors == 0

    def test_multi_child_same_parent(self, in_memory_db: Session, tmp_path: Path):
        """同一父 SKU 多个颜色子 SKU（_Da, _Wh）。"""
        in_memory_db.add(Product(
            sku="MULTI-COLOR",
            title=None,
            asin=None,
            source_url=None,
            cost_price=None,
            cost_currency="JPY",
            status=ProductStatus.ACTIVE,
        ))
        in_memory_db.add(OrderItem(
            order_id="ORDER-001",
            sku="MULTI-COLOR_Da",
            quantity=1,
            unit_price=500.0,
            sale_amount=500.0,
        ))
        in_memory_db.add(OrderItem(
            order_id="ORDER-002",
            sku="MULTI-COLOR_Wh",
            quantity=1,
            unit_price=500.0,
            sale_amount=500.0,
        ))
        in_memory_db.commit()

        with patch("modules.listing.variant_sku_syncer.get_session") as mock_sess:
            mock_sess.return_value.__enter__ = MagicMock(return_value=in_memory_db)
            mock_sess.return_value.__exit__ = MagicMock(return_value=False)
            syncer = VariantSkuSyncer()
            result = syncer.sync_from_order_items()

        assert result.created == 2
        p_da = in_memory_db.get(Product, "MULTI-COLOR_Da")
        p_wh = in_memory_db.get(Product, "MULTI-COLOR_Wh")
        assert p_da.parent_sku == "MULTI-COLOR"
        assert p_da.variant_note == "Suffix: Da"
        assert p_wh.parent_sku == "MULTI-COLOR"
        assert p_wh.variant_note == "Suffix: Wh"

    def test_variant_note_unknown_suffix(self, in_memory_db: Session, tmp_path: Path):
        """未知后缀（_#04, _bl, _fl）→ Suffix: {raw}。"""
        in_memory_db.add(Product(
            sku="UNK-PARENT",
            title=None,
            asin=None,
            source_url=None,
            cost_price=None,
            cost_currency="JPY",
            status=ProductStatus.ACTIVE,
        ))
        in_memory_db.add(OrderItem(
            order_id="ORDER-001",
            sku="UNK-PARENT_#04",
            quantity=1,
            unit_price=500.0,
            sale_amount=500.0,
        ))
        in_memory_db.commit()

        with patch("modules.listing.variant_sku_syncer.get_session") as mock_sess:
            mock_sess.return_value.__enter__ = MagicMock(return_value=in_memory_db)
            mock_sess.return_value.__exit__ = MagicMock(return_value=False)
            syncer = VariantSkuSyncer()
            syncer.sync_from_order_items()

        p = in_memory_db.get(Product, "UNK-PARENT_#04")
        assert p.variant_note == "Suffix: #04"
