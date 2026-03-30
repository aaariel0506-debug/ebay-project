"""
tests/test_generator_html.py — HTML 订单页面生成测试
"""
import os
import pytest
from pathlib import Path
from db.db import init_db, insert, fetch_all
from generator.html_order_page import generate_order_detail, generate_order_receipt
from generator.folder_builder import build_order_folders


@pytest.fixture(scope='function')
def test_db(tmp_path, monkeypatch):
    """为每个测试创建独立的临时数据库"""
    db_path = tmp_path / "test_orders.db"

    from db import db as db_module

    def mock_get_db_path():
        return str(db_path)

    monkeypatch.setattr(db_module, 'get_db_path', mock_get_db_path)

    init_db()
    yield str(db_path)

    if db_path.exists():
        db_path.unlink()


@pytest.fixture
def sample_order_data(test_db):
    """创建示例订单数据"""
    # 插入 eBay 订单
    insert('ebay_orders', {
        'order_id': 'ORDER-HTML-001',
        'sale_date': '2024-01-15',
        'buyer_username': 'html_buyer',
        'item_title': 'HTML Test Item',
        'item_id': 'B0HTML123',
        'quantity': 2,
        'sale_price_usd': 99.99,
        'shipping_charged_usd': 15.00,
        'ebay_fee_usd': 10.00,
        'ebay_ad_fee_usd': 5.00,
        'payment_net_usd': 99.99,
        'order_status': 'Shipped',
        'shipping_address_country': 'US',
    })

    # 插入快递记录
    insert('shipments', {
        'id': 'SHIP-HTML-001',
        'carrier': 'cpass_speedpak',
        'tracking_number': 'TRACK-HTML-001',
        'ebay_order_id': 'ORDER-HTML-001',
        'ship_date': '2024-01-16',
        'shipping_fee_usd': 12.00,
        'cpass_transaction_id': 'TXN-HTML-001',
    })

    # 插入采购记录
    insert('purchases', {
        'id': 'amazon_JP-HTML-001_B0HTML123',
        'platform': 'amazon_jp',
        'purchase_date': '2024-01-10',
        'item_name': 'HTML テスト商品',
        'item_sku': 'B0HTML123',
        'quantity': 1,
        'total_price_jpy': 5000.0,
        'tax_jpy': 500.0,
        'order_number': 'JP-HTML-001',
    })

    # 插入匹配关系
    insert('purchase_order_links', {
        'purchase_id': 'amazon_JP-HTML-001_B0HTML123',
        'ebay_order_id': 'ORDER-HTML-001',
        'match_method': 'sku',
        'confidence': 1.0,
    })

    return test_db


class TestHtmlOrderPage:
    """HTML 订单页面生成测试"""

    def test_generate_order_detail(self, test_db, sample_order_data, tmp_path):
        """测试生成订单详情页"""
        output_path = tmp_path / "order_detail.html"

        result_path = generate_order_detail('ORDER-HTML-001', str(output_path))

        assert result_path == str(output_path)
        assert os.path.exists(result_path)

        # 验证 HTML 内容
        html_content = output_path.read_text(encoding='utf-8')

        # 验证关键字段
        assert 'Order Details' in html_content
        assert 'ORDER-HTML-001' in html_content
        assert 'HTML Test Item' in html_content
        assert 'B0HTML123' in html_content
        assert 'html_buyer' in html_content
        assert 'US' in html_content
        assert '$99.99' in html_content
        assert 'cpass_speedpak' in html_content
        assert 'TRACK-HTML-001' in html_content
        assert 'HTML テスト商品' in html_content
        assert '¥5,000' in html_content

    def test_generate_order_receipt(self, test_db, sample_order_data, tmp_path):
        """测试生成订单收据页"""
        output_path = tmp_path / "order_receipt.html"

        result_path = generate_order_receipt('ORDER-HTML-001', str(output_path))

        assert result_path == str(output_path)
        assert os.path.exists(result_path)

        # 验证 HTML 内容
        html_content = output_path.read_text(encoding='utf-8')

        # 验证关键字段
        assert 'Order Receipt' in html_content
        assert 'ORDER-HTML-001' in html_content
        assert 'eBay' in html_content  # Logo
        assert '$99.99' in html_content
        assert 'Net Amount' in html_content

    def test_generate_order_detail_not_found(self, test_db, tmp_path):
        """测试生成不存在的订单"""
        output_path = tmp_path / "order_detail.html"

        with pytest.raises(ValueError, match="Order not found"):
            generate_order_detail('NON-EXISTENT-ORDER', str(output_path))

    def test_html_single_file(self, test_db, sample_order_data, tmp_path):
        """测试 HTML 是单文件（内联 CSS，无外部依赖）"""
        output_path = tmp_path / "order_detail.html"
        generate_order_detail('ORDER-HTML-001', str(output_path))

        html_content = output_path.read_text(encoding='utf-8')

        # 验证内联 CSS
        assert '<style>' in html_content
        assert '</style>' in html_content

        # 验证无外部 CSS 依赖
        assert '<link rel="stylesheet"' not in html_content

    def test_html_print_media_query(self, test_db, sample_order_data, tmp_path):
        """测试包含打印媒体查询"""
        output_path = tmp_path / "order_detail.html"
        generate_order_detail('ORDER-HTML-001', str(output_path))

        html_content = output_path.read_text(encoding='utf-8')

        assert '@media print' in html_content


class TestFolderBuilder:
    """订单文件夹构建测试"""

    def test_build_order_folders(self, test_db, sample_order_data, tmp_path):
        """测试构建订单文件夹"""
        output_base = str(tmp_path / "output")

        folder_count = build_order_folders(2024, output_base)

        assert folder_count == 1

        # 验证文件夹结构
        order_folder = Path(output_base) / "orders" / "ORDER-HTML-001"
        assert order_folder.exists()

        # 验证 HTML 文件
        assert (order_folder / "01_order_detail.html").exists()
        assert (order_folder / "02_order_receipt.html").exists()

        # 验证空文件夹
        assert (order_folder / "03_shipping_label").exists()
        assert (order_folder / "03_shipping_label").is_dir()
        assert (order_folder / "04_cpass_transaction").exists()
        assert (order_folder / "04_cpass_transaction").is_dir()
        assert (order_folder / "05_japanpost_email").exists()
        assert (order_folder / "05_japanpost_email").is_dir()

        # 验证 README.txt
        readme_path = order_folder / "README.txt"
        assert readme_path.exists()
        readme_content = readme_path.read_text()
        assert 'ORDER-HTML-001' in readme_content
        assert 'Folder Structure' in readme_content

    def test_build_order_folders_empty_year(self, test_db, tmp_path):
        """测试空年份（没有订单）"""
        output_base = str(tmp_path / "output")

        folder_count = build_order_folders(2099, output_base)

        assert folder_count == 0

    def test_build_order_folders_multiple_orders(self, test_db, tmp_path):
        """测试多个订单的文件夹构建"""
        # 插入多个订单
        for i in range(3):
            insert('ebay_orders', {
                'order_id': f'ORDER-MULTI-{i:03d}',
                'sale_date': f'2024-0{i+1}-15',
                'buyer_username': f'buyer{i}',
                'item_title': f'Item {i}',
                'item_id': f'B0MULTI{i:03d}',
                'quantity': 1,
                'sale_price_usd': 50.0,
                'shipping_charged_usd': 5.0,
                'ebay_fee_usd': 5.0,
                'ebay_ad_fee_usd': 0.0,
                'payment_net_usd': 45.0,
                'order_status': 'Shipped',
                'shipping_address_country': 'US',
            })

        output_base = str(tmp_path / "output")
        folder_count = build_order_folders(2024, output_base)

        assert folder_count == 3

        # 验证所有文件夹都存在
        orders_dir = Path(output_base) / "orders"
        for i in range(3):
            order_id = f'ORDER-MULTI-{i:03d}'
            order_folder = orders_dir / order_id
            assert order_folder.exists()
            assert (order_folder / "01_order_detail.html").exists()
            assert (order_folder / "README.txt").exists()
