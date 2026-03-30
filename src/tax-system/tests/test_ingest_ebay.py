"""
tests/test_ingest_ebay.py — eBay 订单导入测试
"""
import os
import tempfile
import pytest
import pandas as pd
from db.db import init_db, fetch_all, execute
from ingest.ebay_orders import ingest_ebay_orders


@pytest.fixture(scope='function')
def test_db(tmp_path, monkeypatch):
    """为每个测试创建独立的临时数据库"""
    db_path = tmp_path / "test_orders.db"
    monkeypatch.setenv('TEST_DB_PATH', str(db_path))

    # 临时修改 get_db_path 函数
    from db import db as db_module
    original_get_db_path = db_module.get_db_path

    def mock_get_db_path():
        return str(db_path)

    monkeypatch.setattr(db_module, 'get_db_path', mock_get_db_path)

    # 初始化数据库
    init_db()
    yield str(db_path)

    # 清理
    if db_path.exists():
        db_path.unlink()


@pytest.fixture
def sample_ebay_csv(tmp_path):
    """创建示例 eBay CSV 文件"""
    csv_path = tmp_path / "ebay_orders.csv"

    # 创建测试数据
    data = {
        'Order Id': ['ORDER-001', 'ORDER-002', 'ORDER-003'],
        'Sale Date': ['2024-01-15', '01/20/2024', '2024/02/10'],
        'Buyer Username': ['buyer1', 'buyer2', 'buyer3'],
        'Item Title': ['Test Item 1', 'Test Item 2', 'Test Item 3'],
        'Item Id': ['ITEM-001', 'ITEM-002', 'ITEM-003'],
        'Quantity': [1, 2, 1],
        'Total Sale Price': ['$100.00', '$250.50', '$75.00'],
        'Shipping Price': ['$10.00', '$15.50', '$5.00'],
        'Final Value Fee': ['$10.00', '$25.00', '$7.50'],
        'Promoted Listing Fee': ['$5.00', '$12.50', '$0.00'],
        'Net Amount': ['$85.00', '$228.00', '$62.50'],
        'Order Status': ['Shipped', 'Shipped', 'Processing'],
        'Ship To Country': ['US', 'UK', 'JP'],
    }

    df = pd.DataFrame(data)
    df.to_csv(csv_path, index=False)
    return str(csv_path)


@pytest.fixture
def sample_ebay_csv_with_commas(tmp_path):
    """创建带逗号的金额字段的 CSV 文件"""
    csv_path = tmp_path / "ebay_orders_commas.csv"

    data = {
        'Order Id': ['ORDER-100'],
        'Sale Date': ['2024-03-01'],
        'Buyer Username': ['buyer100'],
        'Item Title': ['Expensive Item'],
        'Item Id': ['ITEM-100'],
        'Quantity': [1],
        'Total Sale Price': ['$1,234.56'],  # 带逗号
        'Shipping Price': ['$100.00'],
        'Final Value Fee': ['$123.45'],
        'Promoted Listing Fee': ['$50.00'],
        'Net Amount': ['$961.11'],
        'Order Status': ['Shipped'],
        'Ship To Country': ['US'],
    }

    df = pd.DataFrame(data)
    df.to_csv(csv_path, index=False)
    return str(csv_path)


class TestIngestEbayOrders:
    """eBay 订单导入测试"""

    def test_basic_import(self, test_db, sample_ebay_csv):
        """测试基本导入功能"""
        count = ingest_ebay_orders(sample_ebay_csv)
        assert count == 3

        # 验证数据已写入
        orders = fetch_all("SELECT * FROM ebay_orders ORDER BY order_id")
        assert len(orders) == 3

        # 验证第一条记录
        order = orders[0]
        assert order['order_id'] == 'ORDER-001'
        assert order['sale_date'] == '2024-01-15'
        assert order['buyer_username'] == 'buyer1'
        assert order['sale_price_usd'] == 100.0
        assert order['shipping_charged_usd'] == 10.0

    def test_currency_parsing(self, test_db, sample_ebay_csv):
        """测试金额字段解析（去掉$和逗号）"""
        ingest_ebay_orders(sample_ebay_csv)
        orders = fetch_all("SELECT * FROM ebay_orders ORDER BY order_id")

        # 验证金额已正确转换
        assert orders[0]['sale_price_usd'] == 100.0
        assert orders[1]['sale_price_usd'] == 250.5
        assert orders[2]['sale_price_usd'] == 75.0

    def test_currency_with_commas(self, test_db, sample_ebay_csv_with_commas):
        """测试带逗号的金额字段解析"""
        count = ingest_ebay_orders(sample_ebay_csv_with_commas)
        assert count == 1

        orders = fetch_all("SELECT * FROM ebay_orders")
        assert orders[0]['sale_price_usd'] == 1234.56

    def test_date_parsing(self, test_db, sample_ebay_csv):
        """测试日期字段解析（统一转 YYYY-MM-DD）"""
        ingest_ebay_orders(sample_ebay_csv)
        orders = fetch_all("SELECT * FROM ebay_orders ORDER BY order_id")

        # 所有日期都应该是 YYYY-MM-DD 格式
        assert orders[0]['sale_date'] == '2024-01-15'
        assert orders[1]['sale_date'] == '2024-01-20'
        assert orders[2]['sale_date'] == '2024-02-10'

    def test_idempotency(self, test_db, sample_ebay_csv):
        """测试幂等性：重复导入相同数据不会创建重复记录"""
        # 第一次导入
        count1 = ingest_ebay_orders(sample_ebay_csv)
        assert count1 == 3

        # 第二次导入相同数据
        count2 = ingest_ebay_orders(sample_ebay_csv)
        # 由于 INSERT OR IGNORE，不会插入重复数据
        assert count2 == 0  # 或者返回 0，因为数据已存在

        # 验证数据库中只有 3 条记录
        orders = fetch_all("SELECT * FROM ebay_orders")
        assert len(orders) == 3

    def test_empty_file(self, test_db, tmp_path):
        """测试空 CSV 文件"""
        csv_path = tmp_path / "empty.csv"
        csv_path.write_text("Order Id,Sale Date,Buyer Username\n")

        count = ingest_ebay_orders(str(csv_path))
        assert count == 0

    def test_null_values(self, test_db, tmp_path):
        """测试包含空值的 CSV"""
        csv_path = tmp_path / "nulls.csv"

        data = {
            'Order Id': ['ORDER-NULL'],
            'Sale Date': [''],
            'Buyer Username': [''],
            'Item Title': [''],
            'Item Id': [''],
            'Quantity': [1],
            'Total Sale Price': [''],
            'Shipping Price': [''],
            'Final Value Fee': [''],
            'Promoted Listing Fee': [''],
            'Net Amount': [''],
            'Order Status': [''],
            'Ship To Country': [''],
        }

        df = pd.DataFrame(data)
        df.to_csv(csv_path, index=False)

        count = ingest_ebay_orders(str(csv_path))
        assert count == 1

        orders = fetch_all("SELECT * FROM ebay_orders")
        order = orders[0]
        assert order['order_id'] == 'ORDER-NULL'
        assert order['sale_date'] is None
        assert order['buyer_username'] is None
        assert order['sale_price_usd'] is None
