"""
tests/test_ingest_cpass.py — CPass 快递导入测试
"""
import pytest
import pandas as pd
from db.db import init_db, fetch_all, insert
from ingest.cpass import ingest_cpass


@pytest.fixture(scope='function')
def test_db(tmp_path, monkeypatch):
    """为每个测试创建独立的临时数据库"""
    db_path = tmp_path / "test_orders.db"

    from db import db as db_module
    original_get_db_path = db_module.get_db_path

    def mock_get_db_path():
        return str(db_path)

    monkeypatch.setattr(db_module, 'get_db_path', mock_get_db_path)

    init_db()
    yield str(db_path)

    if db_path.exists():
        db_path.unlink()


@pytest.fixture
def sample_cpass_csv(tmp_path):
    """创建示例 CPass CSV 文件（ebay_order_id 为空，避免外键约束）"""
    csv_path = tmp_path / "cpass_shipments.csv"

    data = {
        'cpass_transaction_id': ['TXN-001', 'TXN-002', 'TXN-003'],
        'Carrier': ['SpeedPak Express', 'FedEx International', 'SpeedPak Standard'],
        'Tracking Number': ['TRACK-001', 'TRACK-002', 'TRACK-003'],
        'eBay Order ID': [None, None, None],  # 空值，避免外键约束
        'Ship Date': ['2024-01-15', '01/20/2024', '2024/02/10'],
        'Shipping Fee': ['$10.00', '$25.50', '$8.00'],
    }

    df = pd.DataFrame(data)
    df.to_csv(csv_path, index=False)
    return str(csv_path)


@pytest.fixture
def sample_cpass_csv_with_ebay_orders(tmp_path, test_db):
    """创建示例 CPass CSV 文件（带有有效的 ebay_order_id）"""
    # 先创建 eBay 订单
    insert('ebay_orders', {
        'order_id': 'ORDER-001',
        'sale_date': '2024-01-10',
        'buyer_username': 'buyer1',
    })
    insert('ebay_orders', {
        'order_id': 'ORDER-002',
        'sale_date': '2024-01-15',
        'buyer_username': 'buyer2',
    })

    csv_path = tmp_path / "cpass_shipments.csv"
    data = {
        'cpass_transaction_id': ['TXN-001', 'TXN-002'],
        'Carrier': ['SpeedPak Express', 'FedEx International'],
        'Tracking Number': ['TRACK-001', 'TRACK-002'],
        'eBay Order ID': ['ORDER-001', 'ORDER-002'],
        'Ship Date': ['2024-01-15', '01/20/2024'],
        'Shipping Fee': ['$10.00', '$25.50'],
    }

    df = pd.DataFrame(data)
    df.to_csv(csv_path, index=False)
    return str(csv_path)


@pytest.fixture
def sample_cpass_csv_with_commas(tmp_path):
    """创建带逗号的金额字段的 CSV 文件"""
    csv_path = tmp_path / "cpass_commas.csv"

    data = {
        'cpass_transaction_id': ['TXN-100'],
        'Carrier': ['FedEx Express'],
        'Tracking Number': ['TRACK-100'],
        'eBay Order ID': [None],
        'Ship Date': ['2024-03-01'],
        'Shipping Fee': ['$1,234.56'],
    }

    df = pd.DataFrame(data)
    df.to_csv(csv_path, index=False)
    return str(csv_path)


class TestIngestCpass:
    """CPass 快递导入测试"""

    def test_basic_import(self, test_db, sample_cpass_csv):
        """测试基本导入功能"""
        count = ingest_cpass(sample_cpass_csv)
        assert count == 3

        shipments = fetch_all("SELECT * FROM shipments ORDER BY id")
        assert len(shipments) == 3

        # 验证第一条记录
        shipment = shipments[0]
        assert shipment['id'] == 'cpass_TXN-001'
        assert shipment['carrier'] == 'cpass_speedpak'
        assert shipment['tracking_number'] == 'TRACK-001'
        assert shipment['ebay_order_id'] is None
        assert shipment['ship_date'] == '2024-01-15'
        assert shipment['shipping_fee_usd'] == 10.0

    def test_carrier_mapping_speedpak(self, test_db, sample_cpass_csv):
        """测试 SpeedPak 承运商映射"""
        ingest_cpass(sample_cpass_csv)
        shipments = fetch_all("SELECT * FROM shipments ORDER BY id")

        # TXN-001 和 TXN-003 是 SpeedPak
        assert shipments[0]['carrier'] == 'cpass_speedpak'
        assert shipments[2]['carrier'] == 'cpass_speedpak'

    def test_carrier_mapping_fedex(self, test_db, sample_cpass_csv):
        """测试 FedEx 承运商映射"""
        ingest_cpass(sample_cpass_csv)
        shipments = fetch_all("SELECT * FROM shipments ORDER BY id")

        # TXN-002 是 FedEx
        assert shipments[1]['carrier'] == 'cpass_fedex'

    def test_currency_parsing(self, test_db, sample_cpass_csv):
        """测试金额字段解析"""
        ingest_cpass(sample_cpass_csv)
        shipments = fetch_all("SELECT * FROM shipments ORDER BY id")

        assert shipments[0]['shipping_fee_usd'] == 10.0
        assert shipments[1]['shipping_fee_usd'] == 25.5
        assert shipments[2]['shipping_fee_usd'] == 8.0

    def test_currency_with_commas(self, test_db, sample_cpass_csv_with_commas):
        """测试带逗号的金额字段解析"""
        count = ingest_cpass(sample_cpass_csv_with_commas)
        assert count == 1

        shipments = fetch_all("SELECT * FROM shipments")
        assert shipments[0]['shipping_fee_usd'] == 1234.56

    def test_date_parsing(self, test_db, sample_cpass_csv):
        """测试日期字段解析（统一转 YYYY-MM-DD）"""
        ingest_cpass(sample_cpass_csv)
        shipments = fetch_all("SELECT * FROM shipments ORDER BY id")

        assert shipments[0]['ship_date'] == '2024-01-15'
        assert shipments[1]['ship_date'] == '2024-01-20'
        assert shipments[2]['ship_date'] == '2024-02-10'

    def test_with_ebay_order_link(self, test_db, sample_cpass_csv_with_ebay_orders):
        """测试与 eBay 订单关联的导入"""
        count = ingest_cpass(sample_cpass_csv_with_ebay_orders)
        assert count == 2

        shipments = fetch_all("SELECT * FROM shipments ORDER BY id")
        assert len(shipments) == 2

        # 验证 ebay_order_id 已正确设置
        assert shipments[0]['ebay_order_id'] == 'ORDER-001'
        assert shipments[1]['ebay_order_id'] == 'ORDER-002'

    def test_idempotency(self, test_db, sample_cpass_csv):
        """测试幂等性：重复导入相同数据不会创建重复记录"""
        count1 = ingest_cpass(sample_cpass_csv)
        assert count1 == 3

        count2 = ingest_cpass(sample_cpass_csv)
        assert count2 == 0

        shipments = fetch_all("SELECT * FROM shipments")
        assert len(shipments) == 3

    def test_null_ebay_order_id(self, test_db, sample_cpass_csv):
        """测试 ebay_order_id 为空的记录"""
        ingest_cpass(sample_cpass_csv)
        shipments = fetch_all("SELECT * FROM shipments ORDER BY id")

        # 所有记录的 ebay_order_id 都为空
        for shipment in shipments:
            assert shipment['ebay_order_id'] is None

    def test_empty_file(self, test_db, tmp_path):
        """测试空 CSV 文件"""
        csv_path = tmp_path / "empty.csv"
        csv_path.write_text("cpass_transaction_id,Carrier,Tracking Number\n")

        count = ingest_cpass(str(csv_path))
        assert count == 0

    def test_missing_transaction_id(self, test_db, tmp_path):
        """测试缺少 transaction_id 的行会被跳过"""
        csv_path = tmp_path / "missing_txn.csv"

        data = {
            'cpass_transaction_id': ['TXN-001', None, 'TXN-003'],
            'Carrier': ['SpeedPak', 'SpeedPak', 'SpeedPak'],
            'Tracking Number': ['TRACK-001', 'TRACK-002', 'TRACK-003'],
            'eBay Order ID': [None, None, None],
        }

        df = pd.DataFrame(data)
        df.to_csv(csv_path, index=False)

        count = ingest_cpass(str(csv_path))
        assert count == 2  # 只有 2 条有效记录

        shipments = fetch_all("SELECT * FROM shipments ORDER BY id")
        assert len(shipments) == 2
