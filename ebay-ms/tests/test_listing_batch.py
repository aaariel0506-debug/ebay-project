"""Tests for listing batch importer."""

from __future__ import annotations

import csv
import io
import os
import tempfile
from unittest.mock import patch

import pytest
from modules.listing.importer import (
    ImportResult,
    ImportRow,
    ListingImporter,
    _generate_batch_id,
    _mock_product_from_row,
)

# ── Fixtures ────────────────────────────────────────────────────────────────

@pytest.fixture
def importer() -> ListingImporter:
    return ListingImporter(batch_id="test-batch-001", resume=False)


@pytest.fixture
def sample_csv_content() -> str:
    headers = [
        "sku", "title", "description", "category_id",
        "condition", "condition_description",
        "listing_price", "quantity", "image_urls",
        "fulfillment_policy_id", "return_policy_id", "payment_policy_id",
        "template_id", "variant_sku", "variant_specifics", "is_parent",
    ]
    rows = [
        headers,
        ["SKU001", "Test Product 1", "Description 1", "CAT1", "NEW", "",
         "100", "10", "https://img1.jpg,https://img2.jpg", "", "", "", "", "", "", "FALSE"],
        ["SKU002", "Test Product 2", "Description 2", "CAT2", "USED_GOOD", "",
         "200", "5", "", "", "", "", "", "", "", "FALSE"],
    ]
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerows(rows)
    return output.getvalue()


# ── Test generate_template ─────────────────────────────────────────────────

class TestGenerateTemplate:
    def test_generate_template_returns_string(self, importer: ListingImporter):
        content = importer.generate_template()
        assert isinstance(content, str)
        assert "sku" in content

    def test_generate_template_write_file(self, importer: ListingImporter):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as f:
            path = f.name
        try:
            importer.generate_template(path)
            with open(path, encoding="utf-8") as f:
                content = f.read()
            assert "sku" in content
        finally:
            os.unlink(path)


# ── Test CSV parsing ───────────────────────────────────────────────────────

class TestCSVParsing:
    def test_read_csv_returns_dicts(self, importer: ListingImporter, sample_csv_content: str):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False, encoding="utf-8") as f:
            f.write(sample_csv_content)
            path = f.name
        try:
            rows = importer._read_csv(path, skip_header=True)
            assert len(rows) == 2
            assert rows[0]["sku"] == "SKU001"
            assert rows[1]["sku"] == "SKU002"
        finally:
            os.unlink(path)

    def test_dict_to_row_basic(self, importer: ListingImporter):
        d = {
            "sku": "X001",
            "title": "Product X",
            "description": "Desc",
            "category_id": "CAT",
            "condition": "NEW",
            "listing_price": "123.45",
            "quantity": "7",
            "image_urls": "https://a.jpg,https://b.jpg",
        }
        row = importer._dict_to_row(d)
        assert row.sku == "X001"
        assert row.title == "Product X"
        assert row.listing_price == 123.45
        assert row.quantity == 7
        assert row.image_urls == "https://a.jpg,https://b.jpg"

    def test_dict_to_row_defaults(self, importer: ListingImporter):
        row = importer._dict_to_row({})
        assert row.sku == ""
        assert row.condition == "NEW"
        assert row.is_parent is False

    def test_dict_to_row_is_parent(self, importer: ListingImporter):
        row = importer._dict_to_row({"is_parent": "TRUE"})
        assert row.is_parent is True
        row2 = importer._dict_to_row({"is_parent": "FALSE"})
        assert row2.is_parent is False
        row3 = importer._dict_to_row({"is_parent": "1"})
        assert row3.is_parent is True


# ── Test parse helpers ──────────────────────────────────────────────────────

class TestParseHelpers:
    def test_parse_image_urls_single(self, importer: ListingImporter):
        assert importer._parse_image_urls("https://a.jpg") == ["https://a.jpg"]

    def test_parse_image_urls_multiple(self, importer: ListingImporter):
        result = importer._parse_image_urls("https://a.jpg, https://b.jpg, https://c.jpg")
        assert result == ["https://a.jpg", "https://b.jpg", "https://c.jpg"]

    def test_parse_image_urls_empty(self, importer: ListingImporter):
        assert importer._parse_image_urls("") == []
        assert importer._parse_image_urls(None) == []

    def test_parse_variant_specifics_basic(self, importer: ListingImporter):
        result = importer._parse_variant_specifics("Size:M,Color:Red")
        assert len(result) == 2
        assert result[0].name == "Size"
        assert result[0].value == "M"
        assert result[1].name == "Color"
        assert result[1].value == "Red"

    def test_parse_variant_specifics_single(self, importer: ListingImporter):
        result = importer._parse_variant_specifics("Size:L")
        assert len(result) == 1
        assert result[0].name == "Size"
        assert result[0].value == "L"

    def test_parse_variant_specifics_empty(self, importer: ListingImporter):
        assert importer._parse_variant_specifics("") == []
        assert importer._parse_variant_specifics(None) == []


# ── Test ImportRow dataclass ────────────────────────────────────────────────

class TestImportRow:
    def test_import_row_defaults(self):
        row = ImportRow(sku="X", title="Y")
        assert row.condition == "NEW"
        assert row.is_parent is False
        assert row.variant_sku is None

    def test_import_row_full(self):
        row = ImportRow(
            sku="X", title="Y", description="D", category_id="CAT",
            condition="USED_GOOD", listing_price=99.9, quantity=5,
            image_urls="http://x.jpg", fulfillment_policy_id="fp",
            return_policy_id="rp", payment_policy_id="pp",
            template_id="tpl", variant_sku="VX", variant_specifics="Size:M",
            is_parent=True,
        )
        assert row.sku == "X"
        assert row.is_parent is True
        assert row.variant_specifics == "Size:M"


# ── Test ImportResult ───────────────────────────────────────────────────────

class TestImportResult:
    def test_summary(self):
        result = ImportResult(total_rows=10, success_count=7, failure_count=3)
        assert "7/10" in result.summary()
        assert "3" in result.summary()


# ── Test _mock_product_from_row ─────────────────────────────────────────────

class TestMockProduct:
    def test_mock_product(self):
        row = ImportRow(sku="SKU-X", title="Product X")
        p = _mock_product_from_row(row)
        assert p.sku == "SKU-X"
        assert p.title == "Product X"


# ── Test generate_batch_id ──────────────────────────────────────────────────

class TestBatchId:
    def test_batch_id_format(self):
        bid = _generate_batch_id()
        assert bid.startswith("batch_")
        assert "_" in bid[6:]


# ── Test import_rows (mocked) ───────────────────────────────────────────────

class TestImportRowsMocked:
    def test_import_single_success(self, importer: ListingImporter):
        row = ImportRow(sku="SKU-OK", title="OK Title", listing_price=100, quantity=5)
        # Template path: no template_id → uses ListingCreateRequest directly
        with patch.object(importer.listing_service, "create_single_listing", return_value=None):
            result = importer.import_rows([row])

        assert result.total_rows == 1
        assert result.success_count == 1
        assert result.failure_count == 0
        assert result.completed is True

    def test_import_row_missing_sku_raises(self, importer: ListingImporter):
        row = ImportRow(sku="", title="No SKU")
        with patch.object(importer.listing_service, "create_single_listing"):
            result = importer.import_rows([row])

        assert result.failure_count == 1
        assert result.success_count == 0
        assert "sku" in result.errors[0].message.lower()

    def test_import_file_csv(self, importer: ListingImporter, sample_csv_content: str):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False, encoding="utf-8") as f:
            f.write(sample_csv_content)
            path = f.name

        try:
            with patch.object(importer.listing_service, "create_single_listing"):
                result = importer.import_file(path)

            assert result.total_rows == 2
            assert result.success_count == 2
        finally:
            os.unlink(path)

    def test_resume_from_offset(self, sample_csv_content: str):
        # Create importer with resume and pre-set offset via _start_offset
        imp = ListingImporter(batch_id="resume-test", resume=False)
        imp._start_offset = 1  # Skip first row

        with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False, encoding="utf-8") as f:
            f.write(sample_csv_content)
            path = f.name

        try:
            with patch.object(imp.listing_service, "create_single_listing"):
                result = imp.import_file(path)

            # Only 1 row processed (row 0 skipped)
            assert result.total_rows == 2  # total is raw count
            assert result.last_processed_row == 2  # offset=1: rows 1 and 2 processed
        finally:
            os.unlink(path)
