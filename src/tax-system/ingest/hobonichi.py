"""
ingest/hobonichi.py — ほぼ日ストア (www.1101.com) 订单抓取

登录流程：
  ほぼ日ストア 使用 "ほぼ日ID"（OAuth），登录页在 /store/ 点击账户图标后跳转。
  由于登录可能有验证码或 OAuth 跳转，推荐使用 session 持久化方式：
    第一次：python main.py scrape --source hobonichi --setup
    之后：  python main.py scrape --source hobonichi --from 2026-02-01

订单历史页结构（根据实际页面调整）：
  URL:    https://www.1101.com/store/member/order_history/
  订单行: .order-list .order-item 或类似结构

如果选择器不对，请在 config.yaml 的 hobonichi 下面调整：
  hobonichi:
    selectors:
      email_input: "#email"
      password_input: "#password"
      submit_button: "button[type=submit]"
      order_row: ".order-list-item"
      order_id: ".order-number"
      order_date: ".order-date"
      item_name: ".item-name"
      total_price: ".total-price"
      quantity: ".quantity"
"""
import re
from datetime import datetime

from playwright.async_api import Page, PlaywrightTimeoutError

from db.db import insert_many
from db.models import Purchase
from ingest.scraper_base import ShopScraper


class HobonichiScraper(ShopScraper):
    SITE_KEY = "hobonichi"
    LOGIN_URL = "https://www.1101.com/store/"
    ORDER_HISTORY_URL = "https://www.1101.com/store/member/order_history/"
    LOGGED_IN_SELECTOR = ".member-menu, .mypage-link, [class*='member'], [class*='mypage'], [class*='account']"

    def _sel(self, key: str, default: str) -> str:
        """从 config.yaml 获取可配置的 CSS 选择器"""
        return self.site_config.get("selectors", {}).get(key, default)

    async def _auto_login(self, page: Page) -> bool:
        """
        ほぼ日ID ログイン：
        1. 在购物车页点击账户/登录按钮
        2. 填写 email 和密码
        3. 提交表单
        """
        if not self.username or not self.password:
            return False

        try:
            # 先访问 store 首页，找登录入口
            await page.goto(self.LOGIN_URL, wait_until="networkidle", timeout=30000)
            await page.wait_for_timeout(1500)

            # 尝试点击登录/账户按钮（各种可能的选择器）
            login_selectors = [
                "text=ログイン",
                "text=会員ログイン",
                "[data-action*='login']",
                "a[href*='login']",
                ".login-btn",
                ".header-account",
            ]
            clicked = False
            for sel in login_selectors:
                try:
                    el = await page.query_selector(sel)
                    if el and await el.is_visible():
                        await el.click()
                        await page.wait_for_timeout(2000)
                        clicked = True
                        break
                except Exception:
                    continue

            # 等待登录表单出现
            email_sel = self._sel("email_input", "input[type='email'], input[name*='email'], input[name*='mail'], #email, #mail")
            password_sel = self._sel("password_input", "input[type='password'], #password, input[name*='password']")
            submit_sel = self._sel("submit_button", "button[type='submit'], input[type='submit'], .login-submit, .submit-btn")

            # 等待表单
            await page.wait_for_selector(email_sel, timeout=10000)

            # 填写邮箱
            await page.fill(email_sel, self.username)
            await page.wait_for_timeout(500)

            # 填写密码
            await page.fill(password_sel, self.password)
            await page.wait_for_timeout(500)

            # 点击提交
            await page.click(submit_sel)

            # 等待登录完成（URL 变化或页面元素变化）
            await page.wait_for_timeout(3000)

            return await self._is_logged_in(page)

        except PlaywrightTimeoutError:
            print(f"[hobonichi] 自动登录超时，请使用手动登录模式")
            return False
        except Exception as e:
            print(f"[hobonichi] 自动登录异常: {e}")
            return False

    async def _is_logged_in(self, page: Page) -> bool:
        """检查是否已登录：URL 包含 member 或存在会员专属元素"""
        # 如果 URL 包含 login 或被重定向，说明未登录
        if "login" in page.url.lower():
            return False
        # 检查会员专属元素
        for sel in [".member-menu", ".mypage", ".order-history", "[class*='logout']", "text=ログアウト"]:
            try:
                el = await page.query_selector(sel)
                if el and await el.is_visible():
                    return True
            except Exception:
                continue
        # 如果页面 URL 就是订单历史页，也算登录
        if "order_history" in page.url:
            content = await page.content()
            if "ご注文履歴" in content or "order" in content.lower():
                return True
        return False

    async def parse_orders(
        self,
        page: Page,
        date_from: str | None = None,
        date_to: str | None = None,
    ) -> list[dict]:
        """
        解析 ほぼ日ストア 订单历史页，支持翻页

        配置了 config.yaml hobonichi.selectors 的情况下，可以精确定位。
        否则使用多种通用选择器尝试解析。
        """
        all_purchases = []
        page_num = 0

        while True:
            page_num += 1
            print(f"[hobonichi] 解析第 {page_num} 页...")

            # 等待内容加载
            await page.wait_for_timeout(1000)

            # 获取页面 HTML 内容
            content = await page.content()

            # 尝试多种常见的订单行选择器
            order_row_sel = self._sel("order_row", None)
            if not order_row_sel:
                # 按优先级尝试可能的选择器
                for try_sel in [
                    ".order-list-item",
                    ".order-item",
                    ".order-history-item",
                    "li.order",
                    ".purchase-history-item",
                    "tr.order-row",
                    "[class*='order-list'] > li",
                    "[class*='order-item']",
                    ".receipt-item",
                ]:
                    rows = await page.query_selector_all(try_sel)
                    if rows:
                        order_row_sel = try_sel
                        print(f"[hobonichi] 使用订单行选择器: {try_sel}")
                        break

            if not order_row_sel:
                # 最后手段：提取页面中的订单号和价格
                print("[hobonichi] 未找到标准订单行，尝试从文本提取...")
                purchases = await self._extract_from_text(page, date_from, date_to)
                all_purchases.extend(purchases)
                break

            rows = await page.query_selector_all(order_row_sel)
            if not rows:
                print(f"[hobonichi] 第 {page_num} 页没有订单")
                break

            for row in rows:
                purchase = await self._parse_order_row(row, page)
                if purchase:
                    # 日期范围过滤
                    if date_from and purchase.get("purchase_date") and purchase["purchase_date"] < date_from:
                        continue
                    if date_to and purchase.get("purchase_date") and purchase["purchase_date"] > date_to:
                        continue
                    all_purchases.append(purchase)

            # 翻页
            next_page_sel = self._sel("next_page", "a[rel='next'], .pagination-next, .next-page, button.next, text=次のページ, text=次へ")
            has_next = await self._navigate_next_page(page, next_page_sel)
            if not has_next:
                break

        return all_purchases

    async def _parse_order_row(self, row, page: Page) -> dict | None:
        """从单个订单行 DOM 元素解析数据"""
        try:
            # 提取文字
            row_text = await row.text_content() or ""

            # 订单号
            order_id_sel = self._sel("order_id", "[class*='order-id'], [class*='order-num'], .order-number")
            order_id = ""
            try:
                id_el = await row.query_selector(order_id_sel)
                if id_el:
                    order_id = (await id_el.text_content() or "").strip()
            except Exception:
                pass
            if not order_id:
                # 从文本中提取订单号（数字串）
                m = re.search(r'(?:注文番号|Order[:\s#]*|No\.?\s*)([A-Z0-9\-]+)', row_text, re.I)
                if m:
                    order_id = m.group(1)

            if not order_id:
                return None

            # 日期
            date_sel = self._sel("order_date", "[class*='date'], time")
            order_date = ""
            try:
                date_el = await row.query_selector(date_sel)
                if date_el:
                    dt_attr = await date_el.get_attribute("datetime")
                    order_date = dt_attr or await date_el.text_content() or ""
                    order_date = self._parse_date(order_date.strip())
            except Exception:
                pass
            if not order_date:
                m = re.search(r'(\d{4})[年/\-](\d{1,2})[月/\-](\d{1,2})', row_text)
                if m:
                    order_date = f"{m.group(1)}-{m.group(2).zfill(2)}-{m.group(3).zfill(2)}"

            # 商品名
            name_sel = self._sel("item_name", "[class*='item-name'], [class*='product-name'], [class*='title'], .item-title")
            item_name = ""
            try:
                name_el = await row.query_selector(name_sel)
                if name_el:
                    item_name = (await name_el.text_content() or "").strip()
            except Exception:
                pass

            # 价格（日元）
            price_sel = self._sel("total_price", "[class*='price'], [class*='total'], [class*='amount']")
            total_price_jpy = None
            try:
                price_el = await row.query_selector(price_sel)
                if price_el:
                    price_text = await price_el.text_content() or ""
                    total_price_jpy = self._parse_price(price_text)
            except Exception:
                pass
            if total_price_jpy is None:
                m = re.search(r'[¥￥]\s*([0-9,]+)', row_text)
                if m:
                    total_price_jpy = float(m.group(1).replace(",", ""))

            # 数量
            qty_sel = self._sel("quantity", "[class*='qty'], [class*='quantity'], [class*='count']")
            quantity = 1
            try:
                qty_el = await row.query_selector(qty_sel)
                if qty_el:
                    qty_text = await qty_el.text_content() or ""
                    m = re.search(r'(\d+)', qty_text)
                    if m:
                        quantity = int(m.group(1))
            except Exception:
                pass

            purchase = Purchase(
                id=f"hobonichi_{order_id}",
                platform="hobonichi",
                purchase_date=order_date or None,
                item_name=item_name or row_text[:50].strip() or None,
                quantity=quantity,
                total_price_jpy=total_price_jpy,
                order_number=order_id,
            )
            return purchase.to_dict()
        except Exception as e:
            print(f"[hobonichi] 解析订单行异常: {e}")
            return None

    async def _extract_from_text(
        self,
        page: Page,
        date_from: str | None,
        date_to: str | None,
    ) -> list[dict]:
        """从页面文本中用正则提取订单信息（兜底方案）"""
        content = await page.content()
        purchases = []

        # 尝试找所有包含订单号的块
        # 注文番号 + 日付 + 金額 的典型组合
        blocks = re.findall(
            r'(?:注文番号|Order No\.?)[：:\s]+([A-Z0-9\-]+).*?'
            r'(\d{4})[年/\-](\d{1,2})[月/\-](\d{1,2}).*?'
            r'[¥￥]\s*([0-9,]+)',
            content,
            re.DOTALL | re.I,
        )
        for order_id, year, month, day, price in blocks:
            order_date = f"{year}-{month.zfill(2)}-{day.zfill(2)}"
            if date_from and order_date < date_from:
                continue
            if date_to and order_date > date_to:
                continue
            p = Purchase(
                id=f"hobonichi_{order_id}",
                platform="hobonichi",
                purchase_date=order_date,
                total_price_jpy=float(price.replace(",", "")),
                order_number=order_id,
            )
            purchases.append(p.to_dict())

        return purchases

    def _parse_date(self, text: str) -> str:
        """将各种日期格式统一为 YYYY-MM-DD"""
        if not text:
            return ""
        m = re.search(r'(\d{4})[年/\-](\d{1,2})[月/\-](\d{1,2})', text)
        if m:
            return f"{m.group(1)}-{m.group(2).zfill(2)}-{m.group(3).zfill(2)}"
        try:
            return datetime.fromisoformat(text[:10]).strftime("%Y-%m-%d")
        except Exception:
            return ""

    def _parse_price(self, text: str) -> float | None:
        """从价格文字中提取数字"""
        m = re.search(r'([0-9,]+)', text.replace("¥", "").replace("￥", "").strip())
        if m:
            return float(m.group(1).replace(",", ""))
        return None


def ingest_hobonichi(
    date_from: str | None = None,
    date_to: str | None = None,
    force_relogin: bool = False,
) -> int:
    """
    入口函数：抓取 ほぼ日ストア 订单并写入数据库

    Args:
        date_from: 开始日期 'YYYY-MM-DD'
        date_to:   结束日期 'YYYY-MM-DD'
        force_relogin: 强制重新登录

    Returns:
        实际插入的记录数
    """
    import asyncio

    scraper = HobonichiScraper()
    orders = asyncio.run(
        scraper.scrape(
            date_from=date_from,
            date_to=date_to,
            force_relogin=force_relogin,
        )
    )
    if orders:
        return insert_many("purchases", orders)
    return 0
