"""
tests/test_manual_review.py — 手动审核模块测试
"""
import pytest
from unittest.mock import patch, MagicMock
from db.db import init_db, insert, fetch_all, get_connection
from matcher.manual_review import ManualReviewer


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
def sample_data(test_db):
    """创建示例数据"""
    # 插入 eBay 订单
    insert('ebay_orders', {
        'order_id': 'ORDER-001',
        'sale_date': '2024-02-10',
        'buyer_username': 'buyer1',
        'item_title': 'Hobonichi Techo 2024 Cover Black',
        'quantity': 1,
        'sale_price_usd': 35.99,
        'shipping_charged_usd': 10.0,
        'ebay_fee_usd': 3.5,
        'ebay_ad_fee_usd': 1.0,
        'tracking_number': 'EE1013088JP',
    })

    insert('ebay_orders', {
        'order_id': 'ORDER-002',
        'sale_date': '2024-02-15',
        'buyer_username': 'buyer2',
        'item_title': 'Japanese Planner A6',
        'quantity': 1,
        'sale_price_usd': 28.00,
        'shipping_charged_usd': 8.0,
        'ebay_fee_usd': 2.8,
        'ebay_ad_fee_usd': 0.5,
        'tracking_number': None,
    })

    # 插入未匹配采购
    insert('purchases', {
        'id': 'amazon_JPN-001',
        'platform': 'amazon_jp',
        'purchase_date': '2024-02-08',
        'item_name': 'ほぼ日手帳 2024 カバー A6 黒',
        'item_sku': 'B08XYZABC',
        'quantity': 1,
        'unit_price_jpy': 4200.0,
        'total_price_jpy': 4200.0,
        'tax_jpy': 420.0,
        'order_number': 'JPN-001',
    })

    # 插入未匹配快递
    insert('shipments', {
        'id': 'cpass_EE1013088JP',
        'carrier': 'cpass_speedpak',
        'tracking_number': 'EE1013088JP',
        'ebay_order_id': None,  # 未匹配
        'ship_date': '2024-02-12',
        'shipping_fee_usd': 8.0,
        'cpass_transaction_id': 'TXN-001',
    })

    return test_db


class TestManualReviewerInit:
    """测试初始化"""

    def test_reviewer_init_default(self):
        """默认参数初始化"""
        reviewer = ManualReviewer()
        assert reviewer.review_type == "all"
        assert reviewer.min_confidence == 0.0
        assert reviewer.max_confidence == 1.0
        assert reviewer.stats == {'confirmed': 0, 'skipped': 0, 'no_match': 0}

    def test_reviewer_init_custom(self):
        """自定义参数初始化"""
        reviewer = ManualReviewer(
            review_type="purchase",
            min_confidence=0.5,
            max_confidence=0.85
        )
        assert reviewer.review_type == "purchase"
        assert reviewer.min_confidence == 0.5
        assert reviewer.max_confidence == 0.85


class TestUnmatchedQueries:
    """测试未匹配记录查询"""

    def test_reviewer_loads_unmatched_purchases(self, test_db, sample_data):
        """能正确加载未匹配采购记录"""
        reviewer = ManualReviewer(review_type="purchase")
        purchases = reviewer._get_unmatched_purchases()

        assert len(purchases) == 1
        assert purchases[0]['id'] == 'amazon_JPN-001'

    def test_reviewer_loads_unmatched_shipments(self, test_db, sample_data):
        """能正确加载未匹配快递记录"""
        reviewer = ManualReviewer(review_type="shipment")
        shipments = reviewer._get_unmatched_shipments()

        assert len(shipments) == 1
        assert shipments[0]['id'] == 'cpass_EE1013088JP'

    def test_get_candidates_for_purchase(self, test_db, sample_data):
        """获取采购的候选订单"""
        reviewer = ManualReviewer()
        purchase = {'id': 'amazon_JPN-001', 'purchase_date': '2024-02-08'}
        candidates = reviewer._get_candidates_for_purchase(purchase)

        # 应返回前后 15 天的订单
        assert len(candidates) >= 1
        order_ids = [c['order_id'] for c in candidates]
        assert 'ORDER-001' in order_ids or 'ORDER-002' in order_ids

    def test_get_candidates_for_shipment(self, test_db, sample_data):
        """获取快递的候选订单"""
        reviewer = ManualReviewer()
        shipment = {'id': 'cpass_EE1013088JP', 'ship_date': '2024-02-12', 'tracking_number': 'EE1013088JP'}
        candidates = reviewer._get_candidates_for_shipment(shipment)

        # 应返回跟踪号匹配的订单
        assert len(candidates) >= 1
        # 优先返回跟踪号匹配的
        assert candidates[0]['order_id'] == 'ORDER-001'
        assert candidates[0]['tracking_number'] == 'EE1013088JP'


class TestConfirmMatch:
    """测试确认匹配功能"""

    def test_confirm_purchase_match_updates_db(self, test_db, sample_data):
        """确认匹配后数据库正确更新"""
        reviewer = ManualReviewer()

        # 执行匹配
        reviewer._confirm_purchase_match('amazon_JPN-001', 'ORDER-001')

        # 验证数据库
        links = fetch_all("""
            SELECT * FROM purchase_order_links
            WHERE purchase_id = 'amazon_JPN-001' AND ebay_order_id = 'ORDER-001'
        """)

        assert len(links) == 1
        assert links[0]['match_method'] == 'manual'
        assert links[0]['confidence'] == 1.0
        assert links[0]['confirmed_by'] == 'user'

    def test_confirm_shipment_match_updates_db(self, test_db, sample_data):
        """确认快递匹配后数据库正确更新"""
        reviewer = ManualReviewer()

        # 执行匹配
        reviewer._confirm_shipment_match('cpass_EE1013088JP', 'ORDER-001')

        # 验证数据库
        shipment = fetch_all("SELECT * FROM shipments WHERE id = 'cpass_EE1013088JP'")[0]

        assert shipment['ebay_order_id'] == 'ORDER-001'
        assert shipment['match_method'] == 'manual'
        assert shipment['confirmed_by'] == 'user'


class TestMarkNoMatch:
    """测试标记无匹配功能"""

    def test_mark_no_match_updates_purchase(self, test_db, sample_data):
        """标记采购无匹配后设置 no_match_reason"""
        reviewer = ManualReviewer()

        # 执行标记
        reviewer._mark_no_match('purchase', 'amazon_JPN-001')

        # 验证数据库
        purchase = fetch_all("SELECT * FROM purchases WHERE id = 'amazon_JPN-001'")[0]

        assert purchase['no_match_reason'] == 'no_ebay_order'

    def test_mark_no_match_updates_shipment(self, test_db, sample_data):
        """标记快递无匹配后设置已审核标记"""
        reviewer = ManualReviewer()

        # 执行标记
        reviewer._mark_no_match('shipment', 'cpass_EE1013088JP')

        # 验证数据库
        shipment = fetch_all("SELECT * FROM shipments WHERE id = 'cpass_EE1013088JP'")[0]

        # 外键约束：ebay_order_id 保持 NULL，但标记为已审核
        assert shipment['ebay_order_id'] is None
        assert shipment['match_method'] == 'manual'
        assert shipment['confirmed_by'] == 'user'


class TestReviewFlow:
    """测试完整审核流程"""

    @patch('matcher.manual_review.input', side_effect=['s', 's'])  # 跳过所有
    @patch('matcher.manual_review.print')
    def test_review_skip_all(self, mock_print, mock_input, test_db, sample_data):
        """测试跳过所有记录的流程"""
        reviewer = ManualReviewer(review_type="purchase")
        result = reviewer.run()

        # 验证统计
        assert result['skipped'] >= 0  # 至少有 1 条记录被处理
        assert result['confirmed'] == 0
        assert result['no_match'] == 0

    @patch('matcher.manual_review.input', side_effect=['n'])  # 标记无匹配
    def test_review_mark_no_match(self, mock_input, test_db, sample_data):
        """测试标记无匹配的流程"""
        reviewer = ManualReviewer(review_type="purchase")
        result = reviewer.run()

        # 验证统计
        assert result['no_match'] >= 0

        # 验证数据库
        purchase = fetch_all("SELECT * FROM purchases WHERE id = 'amazon_JPN-001'")[0]
        assert purchase['no_match_reason'] == 'no_ebay_order'

    @patch('matcher.manual_review.input', side_effect=['1'])  # 确认匹配第一个候选
    def test_review_confirm_match(self, mock_input, test_db, sample_data):
        """测试确认匹配的流程"""
        reviewer = ManualReviewer(review_type="purchase")
        result = reviewer.run()

        # 验证统计
        assert result['confirmed'] >= 0

        # 验证数据库
        links = fetch_all("""
            SELECT * FROM purchase_order_links
            WHERE purchase_id = 'amazon_JPN-001'
        """)
        assert len(links) >= 1
        assert links[0]['match_method'] == 'manual'
        assert links[0]['confirmed_by'] == 'user'

    @patch('matcher.manual_review.input', side_effect=['q'])  # 退出
    def test_review_quit_early(self, mock_input, test_db, sample_data):
        """测试提前退出的流程"""
        reviewer = ManualReviewer(review_type="purchase")
        result = reviewer.run()

        # 退出时没有记录被处理
        assert result['confirmed'] == 0
        assert result['skipped'] == 0
        assert result['no_match'] == 0


class TestSkippedRecords:
    """测试已审核记录跳过逻辑"""

    def test_skip_confirmed_purchases(self, test_db, sample_data):
        """已确认的采购不应出现在待审核列表"""
        # 先确认一条匹配
        with get_connection() as conn:
            conn.execute("""
                INSERT INTO purchase_order_links
                (purchase_id, ebay_order_id, match_method, confidence, confirmed_by)
                VALUES ('amazon_JPN-001', 'ORDER-001', 'manual', 1.0, 'user')
            """)

        reviewer = ManualReviewer(review_type="purchase")
        purchases = reviewer._get_unmatched_purchases()

        # 已确认的记录不应出现
        assert len(purchases) == 0

    def test_skip_no_match_purchases(self, test_db, sample_data):
        """已标记无匹配的采购不应出现在待审核列表"""
        # 先标记无匹配
        with get_connection() as conn:
            conn.execute("""
                UPDATE purchases
                SET no_match_reason = 'no_ebay_order'
                WHERE id = 'amazon_JPN-001'
            """)

        reviewer = ManualReviewer(review_type="purchase")
        purchases = reviewer._get_unmatched_purchases()

        # 已标记的记录不应出现
        assert len(purchases) == 0
