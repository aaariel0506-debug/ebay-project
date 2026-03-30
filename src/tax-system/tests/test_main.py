"""
tests/test_main.py — CLI 主程序测试
"""
import pytest
from click.testing import CliRunner
from main import cli, init, ingest


class TestMainCLI:
    """CLI 主程序测试"""

    def test_init_command(self, tmp_path, monkeypatch):
        """测试 init 命令"""
        db_path = tmp_path / "test.db"

        # 修改 get_db_path 函数
        from db import db as db_module

        def mock_get_db_path():
            return str(db_path)

        monkeypatch.setattr(db_module, 'get_db_path', mock_get_db_path)

        runner = CliRunner()
        result = runner.invoke(init)

        assert result.exit_code == 0
        assert "数据库初始化完成" in result.output
        assert db_path.exists()

    def test_ingest_ebay_command(self, tmp_path, monkeypatch):
        """测试 ingest ebay 命令"""
        import pandas as pd

        # 创建测试 CSV
        csv_path = tmp_path / "test_ebay.csv"
        data = {
            'Order Id': ['ORDER-TEST'],
            'Sale Date': ['2024-01-15'],
            'Buyer Username': ['buyer_test'],
            'Item Title': ['Test Item'],
            'Item Id': ['ITEM-TEST'],
            'Quantity': [1],
            'Total Sale Price': ['$50.00'],
            'Shipping Price': ['$5.00'],
            'Final Value Fee': ['$5.00'],
            'Promoted Listing Fee': ['$2.00'],
            'Net Amount': ['$38.00'],
            'Order Status': ['Shipped'],
            'Ship To Country': ['US'],
        }
        df = pd.DataFrame(data)
        df.to_csv(csv_path, index=False)

        # 修改数据库路径
        db_path = tmp_path / "test.db"
        from db import db as db_module

        def mock_get_db_path():
            return str(db_path)

        monkeypatch.setattr(db_module, 'get_db_path', mock_get_db_path)

        # 先初始化数据库
        from db.db import init_db
        init_db()

        runner = CliRunner()
        result = runner.invoke(ingest, ['--source', 'ebay', '--file', str(csv_path)])

        assert result.exit_code == 0
        assert "导入" in result.output
        assert "eBay 订单" in result.output

    def test_ingest_cpass_command(self, tmp_path, monkeypatch):
        """测试 ingest cpass 命令"""
        import pandas as pd

        # 创建测试 CSV
        csv_path = tmp_path / "test_cpass.csv"
        data = {
            'cpass_transaction_id': ['TXN-TEST'],
            'Carrier': ['SpeedPak Express'],
            'Tracking Number': ['TRACK-TEST'],
            'eBay Order ID': [None],
            'Ship Date': ['2024-01-16'],
            'Shipping Fee': ['$10.00'],
        }
        df = pd.DataFrame(data)
        df.to_csv(csv_path, index=False)

        # 修改数据库路径
        db_path = tmp_path / "test.db"
        from db import db as db_module

        def mock_get_db_path():
            return str(db_path)

        monkeypatch.setattr(db_module, 'get_db_path', mock_get_db_path)

        # 先初始化数据库
        from db.db import init_db
        init_db()

        runner = CliRunner()
        result = runner.invoke(ingest, ['--source', 'cpass', '--file', str(csv_path)])

        assert result.exit_code == 0
        assert "导入" in result.output
        assert "CPass" in result.output

    def test_ingest_amazon_jp_command(self, tmp_path, monkeypatch):
        """测试 ingest amazon_jp 命令"""
        import pandas as pd

        # 创建测试 CSV
        csv_path = tmp_path / "test_amazon.csv"
        data = {
            '注文番号': ['JP-ORDER-TEST'],
            'ASIN': ['B0TEST123'],
            '注文日': ['2024/01/15'],
            '商品名': ['テスト商品'],
            '商品の数量': [1],
            '商品の価格（注文時の税抜金額）': ['1000'],
            '商品の小計（税込）': ['1100'],
            '商品の小計（消費税）': ['100'],
            '商品の配送料および手数料（税込）': ['500'],
        }
        df = pd.DataFrame(data)
        df.to_csv(csv_path, index=False, encoding='utf-8-sig')

        # 修改数据库路径
        db_path = tmp_path / "test.db"
        from db import db as db_module

        def mock_get_db_path():
            return str(db_path)

        monkeypatch.setattr(db_module, 'get_db_path', mock_get_db_path)

        # 先初始化数据库
        from db.db import init_db
        init_db()

        runner = CliRunner()
        result = runner.invoke(ingest, ['--source', 'amazon_jp', '--file', str(csv_path)])

        assert result.exit_code == 0
        assert "导入" in result.output
        assert "日本亚马逊" in result.output

    def test_ingest_missing_file(self):
        """测试 ingest 命令缺少文件参数"""
        runner = CliRunner()
        result = runner.invoke(ingest, ['--source', 'ebay'])

        assert result.exit_code == 0
        assert "请指定 --file 参数" in result.output

    def test_ingest_unknown_source(self):
        """测试 ingest 命令未知数据源"""
        runner = CliRunner()
        result = runner.invoke(ingest, ['--source', 'unknown'])

        assert result.exit_code == 0
        assert "未知的数据源" in result.output

    def test_ingest_not_implemented_source(self, tmp_path, monkeypatch):
        """测试 ingest 命令待实现的数据源"""
        # 创建空文件
        test_file = tmp_path / "test.csv"
        test_file.write_text("")

        # 修改数据库路径
        db_path = tmp_path / "test.db"
        from db import db as db_module

        def mock_get_db_path():
            return str(db_path)

        monkeypatch.setattr(db_module, 'get_db_path', mock_get_db_path)

        # 先初始化数据库
        from db.db import init_db
        init_db()

        runner = CliRunner()
        result = runner.invoke(ingest, ['--source', 'hobonichi', '--file', str(test_file)])

        assert result.exit_code == 0
        assert "待实现" in result.output
