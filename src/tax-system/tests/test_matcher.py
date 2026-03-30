"""
tests/test_matcher.py — 匹配引擎测试
"""
import pytest
from db.db import init_db, insert, fetch_all, execute
from matcher.order_shipment import match_order_shipment
from matcher.purchase_order import match_purchase_order


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
def sample_data_for_shipment_matching(test_db):
    """创建用于快递匹配的测试数据"""
    # 插入 eBay 订单
    insert('ebay_orders', {
        'order_id': 'ORDER-001',
        'sale_date': '2024-01-15',
        'buyer_username': 'buyer1',
        'item_title': 'Test Item',
        'item_id': 'ITEM-001',
        'shipping_address_country': 'US',
    })

    insert('ebay_orders', {
        'order_id': 'ORDER-002',
        'sale_date': '2024-02-20',
        'buyer_username': 'buyer2',
        'item_title': 'Another Item',
        'item_id': 'ITEM-002',
        'shipping_address_country': 'UK',
    })

    # 插入shipment（ebay_order_id 为空，待匹配）
    insert('shipments', {
        'id': 'SHIP-001',
        'carrier': 'cpass_speedpak',
        'tracking_number': 'TRACK-001',
        'ebay_order_id': None,  # 待匹配
        'ship_date': '2024-01-16',  # 在 ORDER-001 成交日 +1 天
    })

    insert('shipments', {
        'id': 'SHIP-002',
        'carrier': 'cpass_fedex',
        'tracking_number': 'TRACK-002',
        'ebay_order_id': None,  # 待匹配
        'ship_date': '2024-02-21',  # 在 ORDER-002 成交日 +1 天
    })

    # 插入一个日期不匹配的 shipment
    insert('shipments', {
        'id': 'SHIP-NOMATCH',
        'carrier': 'cpass_speedpak',
        'tracking_number': 'TRACK-NOMATCH',
        'ebay_order_id': None,
        'ship_date': '2024-06-01',  # 与任何订单日期都不匹配
    })

    return test_db


@pytest.fixture
def sample_data_for_purchase_matching(test_db):
    """创建用于采购匹配的测试数据"""
    # 插入 eBay 订单
    insert('ebay_orders', {
        'order_id': 'ORDER-ASIN',
        'sale_date': '2024-01-15',
        'buyer_username': 'buyer1',
        'item_title': 'Test Product',
        'item_id': 'B0TEST123',  # ASIN
    })

    insert('ebay_orders', {
        'order_id': 'ORDER-FUZZY-HIGH',
        'sale_date': '2024-01-20',
        'buyer_username': 'buyer2',
        'item_title': 'Blue Widget Pro',  # 与采购商品名高度相似
        'item_id': 'B0FUZZYHIGH',  # 不与任何采购的 SKU 匹配
    })

    insert('ebay_orders', {
        'order_id': 'ORDER-FUZZY-LOW',
        'sale_date': '2024-01-25',
        'buyer_username': 'buyer3',
        'item_title': 'Red Gadget Mini',  # 与采购商品名相似度低
        'item_id': 'B0FUZZYLOW',  # 不与任何采购的 SKU 匹配
    })

    # 插入采购记录 - ASIN 精确匹配
    insert('purchases', {
        'id': 'amazon_JP-ORDER-1_B0TEST123',
        'platform': 'amazon_jp',
        'purchase_date': '2024-01-10',
        'item_name': 'テスト商品',
        'item_sku': 'B0TEST123',  # 与 ORDER-ASIN 的 item_id 相同
        'quantity': 1,
        'total_price_jpy': 5000.0,
        'tax_jpy': 500.0,
        'order_number': 'JP-ORDER-1',
    })

    # 插入采购记录 - 模糊匹配（高相似度）
    insert('purchases', {
        'id': 'amazon_JP-ORDER-2_B0WIDGET',
        'platform': 'amazon_jp',
        'purchase_date': '2024-01-15',
        'item_name': 'Pro Widget Blue',  # 与 "Blue Widget Pro" 词序不同但相似度高
        'item_sku': 'B0WIDGET',
        'quantity': 1,
        'total_price_jpy': 3000.0,
        'tax_jpy': 300.0,
        'order_number': 'JP-ORDER-2',
    })

    # 插入采购记录 - 模糊匹配（低相似度，低于阈值）
    insert('purchases', {
        'id': 'amazon_JP-ORDER-3_B0GADGET',
        'platform': 'amazon_jp',
        'purchase_date': '2024-01-18',
        'item_name': 'Mini Gadget Red Special',  # 与 "Red Gadget Mini" 相似度较低
        'item_sku': 'B0GADGET',
        'quantity': 1,
        'total_price_jpy': 2000.0,
        'tax_jpy': 200.0,
        'order_number': 'JP-ORDER-3',
    })

    return test_db


class TestOrderShipmentMatching:
    """订单与快递匹配测试"""

    def test_shipment_matching_basic(self, test_db, sample_data_for_shipment_matching):
        """测试基本快递匹配功能"""
        result = match_order_shipment()

        # SHIP-001 和 SHIP-002 应该匹配成功
        assert result['matched'] == 2
        # SHIP-NOMATCH 未匹配
        assert result['unmatched'] == 1

        # 验证数据库已更新
        shipments = fetch_all("SELECT * FROM shipments ORDER BY id")
        ship_001 = [s for s in shipments if s['id'] == 'SHIP-001'][0]
        ship_002 = [s for s in shipments if s['id'] == 'SHIP-002'][0]

        assert ship_001['ebay_order_id'] == 'ORDER-001'
        assert ship_002['ebay_order_id'] == 'ORDER-002'

    def test_shipment_matching_idempotency(self, test_db, sample_data_for_shipment_matching):
        """测试幂等性：重复运行不产生重复匹配"""
        # 第一次运行
        result1 = match_order_shipment()
        matched1 = result1['matched']

        # 第二次运行
        result2 = match_order_shipment()
        # 第二次应该没有新匹配（因为都已匹配）
        assert result2['matched'] == 0


class TestPurchaseOrderMatching:
    """采购与订单匹配测试"""

    def test_asin_exact_match(self, test_db, sample_data_for_purchase_matching):
        """测试 ASIN 精确匹配"""
        result = match_purchase_order()

        # 至少 ASIN 精确匹配的那条应该成功
        assert result['matched'] >= 1

        # 验证 links 表
        links = fetch_all("SELECT * FROM purchase_order_links")

        # 找到 ASIN 精确匹配的记录
        asin_match = None
        for link in links:
            if link['purchase_id'] == 'amazon_JP-ORDER-1_B0TEST123':
                asin_match = link
                break

        assert asin_match is not None
        assert asin_match['ebay_order_id'] == 'ORDER-ASIN'
        assert asin_match['match_method'] == 'sku'
        assert asin_match['confidence'] == 1.0

    def test_fuzzy_match_threshold(self, test_db, sample_data_for_purchase_matching):
        """测试模糊匹配阈值边界（84 不匹配，85 匹配）"""
        result = match_purchase_order()

        # 验证 links 表
        links = fetch_all("SELECT * FROM purchase_order_links")

        # 高相似度应该匹配
        high_match = [l for l in links if l['purchase_id'] == 'amazon_JP-ORDER-2_B0WIDGET']
        assert len(high_match) == 1
        assert high_match[0]['match_method'] == 'fuzzy'
        assert high_match[0]['confidence'] >= 0.85

        # 低相似度不应该匹配
        low_match = [l for l in links if l['purchase_id'] == 'amazon_JP-ORDER-3_B0GADGET']
        assert len(low_match) == 0

    def test_idempotency(self, test_db, sample_data_for_purchase_matching):
        """测试重复运行不产生重复 links 记录"""
        # 第一次运行
        result1 = match_purchase_order()
        matched1 = result1['matched']

        # 第二次运行
        result2 = match_purchase_order()
        # 第二次应该没有新匹配
        assert result2['matched'] == 0

        # 验证 links 表记录数不变
        links = fetch_all("SELECT * FROM purchase_order_links")
        assert len(links) == matched1

    def test_confidence_value(self, test_db, sample_data_for_purchase_matching):
        """测试置信度值正确写入"""
        match_purchase_order()

        links = fetch_all("SELECT * FROM purchase_order_links")

        for link in links:
            assert 0 < link['confidence'] <= 1.0


class TestCombinedMatching:
    """完整匹配流程测试"""

    def test_full_pipeline(self, test_db):
        """测试完整的匹配流程"""
        # 设置测试数据
        insert('ebay_orders', {
            'order_id': 'ORDER-FULL',
            'sale_date': '2024-03-01',
            'buyer_username': 'fullbuyer',
            'item_title': 'Full Test Item',
            'item_id': 'B0FULL123',
        })

        insert('purchases', {
            'id': 'amazon_JP-FULL_B0FULL123',
            'platform': 'amazon_jp',
            'purchase_date': '2024-02-25',
            'item_name': 'フルテスト商品',
            'item_sku': 'B0FULL123',
            'quantity': 1,
            'total_price_jpy': 10000.0,
        })

        insert('shipments', {
            'id': 'SHIP-FULL',
            'carrier': 'cpass_speedpak',
            'tracking_number': 'TRACK-FULL',
            'ebay_order_id': None,
            'ship_date': '2024-03-02',
        })

        # 运行匹配
        from matcher.order_shipment import match_order_shipment
        from matcher.purchase_order import match_purchase_order

        shipment_result = match_order_shipment()
        purchase_result = match_purchase_order()

        # 验证结果
        assert shipment_result['matched'] >= 1
        assert purchase_result['matched'] >= 1
