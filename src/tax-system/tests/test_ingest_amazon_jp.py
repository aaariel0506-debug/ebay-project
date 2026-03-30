"""
tests/test_ingest_amazon_jp.py — 日本亚马逊订单导入测试
"""
import pytest
import pandas as pd
from db.db import init_db, fetch_all
from ingest.amazon_jp import ingest_amazon_jp


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
def sample_amazon_csv(tmp_path):
    """创建示例日本亚马逊 CSV 文件（UTF-8 with BOM）"""
    csv_path = tmp_path / "amazon_jp_orders.csv"

    # 创建测试数据，3 行商品
    data = {
        '注文番号': ['JP-ORDER-001', 'JP-ORDER-001', 'JP-ORDER-002'],
        'ASIN': ['B001ABC123', 'B002DEF456', 'B003GHI789'],
        '注文日': ['2024/01/15', '2024/01/15', '2024/02/20'],
        '商品名': ['テスト商品 1', 'テスト商品 2', 'テスト商品 3'],
        '商品の数量': [1, 2, 1],
        '商品の価格（注文時の税抜金額）': ['1000', '2000', '1500'],
        '商品の小計（税込）': ['1100', '2200', '1650'],
        '商品の小計（消費税）': ['100', '200', '150'],
        '商品の配送料および手数料（税込）': ['500', '500', '600'],
    }

    df = pd.DataFrame(data)
    # 保存为 UTF-8 with BOM
    df.to_csv(csv_path, index=False, encoding='utf-8-sig')
    return str(csv_path)


@pytest.fixture
def sample_amazon_csv_excel_format(tmp_path):
    """创建含 Excel 公式格式的 CSV 文件"""
    csv_path = tmp_path / "amazon_excel_format.csv"

    # 包含 Excel 公式格式 ="6321" 的数据
    data = {
        '注文番号': ['JP-ORDER-EXCEL'],
        'ASIN': ['B0EXCEL123'],
        '注文日': ['2024/03/01'],
        '商品名': ['Excel 商品'],
        '商品の数量': ['="2"'],  # Excel 公式格式
        '商品の価格（注文時の税抜金額）': ['="5000"'],  # Excel 公式格式
        '商品の小計（税込）': ['="5500"'],
        '商品の小計（消費税）': ['="500"'],
        '商品の配送料および手数料（税込）': ['="800"'],
    }

    df = pd.DataFrame(data)
    df.to_csv(csv_path, index=False, encoding='utf-8-sig')
    return str(csv_path)


@pytest.fixture
def sample_amazon_csv_none_values(tmp_path):
    """创建含「該当無し」的 CSV 文件"""
    csv_path = tmp_path / "amazon_none_values.csv"

    # 包含「該当無し」和空值的数据
    data = {
        '注文番号': ['JP-ORDER-NONE'],
        'ASIN': ['B0NONE123'],
        '注文日': ['2024/03/05'],
        '商品名': ['該当無し商品'],
        '商品の数量': ['該当無し'],  # 該当無し
        '商品の価格（注文時の税抜金額）': [''],  # 空字符串
        '商品の小計（税込）': ['該当無し'],
        '商品の小計（消費税）': ['該当無し'],
        '商品の配送料および手数料（税込）': ['300'],
    }

    df = pd.DataFrame(data)
    df.to_csv(csv_path, index=False, encoding='utf-8-sig')
    return str(csv_path)


class TestIngestAmazonJp:
    """日本亚马逊订单导入测试"""

    def test_basic_import(self, test_db, sample_amazon_csv):
        """测试正常导入 3 行 mock 数据"""
        count = ingest_amazon_jp(sample_amazon_csv)
        assert count == 3

        purchases = fetch_all("SELECT * FROM purchases ORDER BY id")
        assert len(purchases) == 3

        # 验证第一条记录
        purchase = purchases[0]
        assert purchase['id'] == 'amazon_jp_JP-ORDER-001_B001ABC123'
        assert purchase['platform'] == 'amazon_jp'
        assert purchase['purchase_date'] == '2024-01-15'
        assert purchase['item_name'] == 'テスト商品 1'
        assert purchase['item_sku'] == 'B001ABC123'
        assert purchase['quantity'] == 1
        assert purchase['unit_price_jpy'] == 1000.0
        assert purchase['total_price_jpy'] == 1100.0
        assert purchase['tax_jpy'] == 100.0
        assert purchase['shipping_fee_jpy'] == 500.0
        assert purchase['order_number'] == 'JP-ORDER-001'

    def test_date_parsing(self, test_db, sample_amazon_csv):
        """测试日期格式转换 YYYY/MM/DD → YYYY-MM-DD"""
        ingest_amazon_jp(sample_amazon_csv)
        purchases = fetch_all("SELECT * FROM purchases ORDER BY id")

        # 所有日期都应该是 YYYY-MM-DD 格式
        assert purchases[0]['purchase_date'] == '2024-01-15'
        assert purchases[2]['purchase_date'] == '2024-02-20'

    def test_excel_format_parsing(self, test_db, sample_amazon_csv_excel_format):
        """测试 Excel 公式格式 ="6321" 的字段能被正确解析"""
        count = ingest_amazon_jp(sample_amazon_csv_excel_format)
        assert count == 1

        purchases = fetch_all("SELECT * FROM purchases")
        purchase = purchases[0]

        # Excel 格式的值应该被正确解析
        assert purchase['quantity'] == 2
        assert purchase['unit_price_jpy'] == 5000.0
        assert purchase['total_price_jpy'] == 5500.0
        assert purchase['tax_jpy'] == 500.0
        assert purchase['shipping_fee_jpy'] == 800.0

    def test_none_values_parsing(self, test_db, sample_amazon_csv_none_values):
        """测试「該当無し」被转为 None"""
        count = ingest_amazon_jp(sample_amazon_csv_none_values)
        assert count == 1

        purchases = fetch_all("SELECT * FROM purchases")
        purchase = purchases[0]

        # 該当無し和空字符串应该被转为 None
        assert purchase['quantity'] == 1  # 默认值
        assert purchase['unit_price_jpy'] is None
        assert purchase['total_price_jpy'] is None
        assert purchase['tax_jpy'] is None
        assert purchase['shipping_fee_jpy'] == 300.0

    def test_idempotency(self, test_db, sample_amazon_csv):
        """测试幂等性：重复导入行数不增加"""
        count1 = ingest_amazon_jp(sample_amazon_csv)
        assert count1 == 3

        count2 = ingest_amazon_jp(sample_amazon_csv)
        assert count2 == 0  # 由于 INSERT OR IGNORE，不会重复插入

        purchases = fetch_all("SELECT * FROM purchases")
        assert len(purchases) == 3

    def test_same_order_multiple_items(self, test_db, sample_amazon_csv):
        """测试同一订单多个商品的导入（注文番号相同，ASIN 不同）"""
        ingest_amazon_jp(sample_amazon_csv)
        purchases = fetch_all("SELECT * FROM purchases ORDER BY id")

        # JP-ORDER-001 有 2 个商品
        order_001_items = [p for p in purchases if p['order_number'] == 'JP-ORDER-001']
        assert len(order_001_items) == 2

        # 验证 ID 不同（因为 ASIN 不同）
        assert order_001_items[0]['id'] != order_001_items[1]['id']

    def test_empty_file(self, test_db, tmp_path):
        """测试空 CSV 文件"""
        csv_path = tmp_path / "empty.csv"
        csv_path.write_text("注文番号，ASIN，注文日\n", encoding='utf-8-sig')

        count = ingest_amazon_jp(str(csv_path))
        assert count == 0

    def test_missing_required_fields(self, test_db, tmp_path):
        """测试缺少必需字段（注文番号或 ASIN）的行会被跳过"""
        csv_path = tmp_path / "missing_fields.csv"

        data = {
            '注文番号': ['JP-ORDER-001', None, 'JP-ORDER-003'],
            'ASIN': [None, 'B002', 'B003'],  # 第一行缺少 ASIN，第二行缺少注文番号
            '注文日': ['2024/01/01', '2024/01/02', '2024/01/03'],
            '商品名': ['商品 1', '商品 2', '商品 3'],
            '商品の数量': [1, 1, 1],
            '商品の価格（注文時の税抜金額）': [1000, 2000, 3000],
            '商品の小計（税込）': [1100, 2200, 3300],
            '商品の小計（消費税）': [100, 200, 300],
            '商品の配送料および手数料（税込）': [500, 500, 500],
        }

        df = pd.DataFrame(data)
        df.to_csv(csv_path, index=False, encoding='utf-8-sig')

        count = ingest_amazon_jp(str(csv_path))
        # 只有 JP-ORDER-003 是有效的（有注文番号和 ASIN）
        assert count == 1

        purchases = fetch_all("SELECT * FROM purchases")
        assert len(purchases) == 1
        assert purchases[0]['order_number'] == 'JP-ORDER-003'
