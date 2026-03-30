"""
ingest/bandai.py — Premium Bandai (p-bandai.jp) 订单抓取

Premium Bandai 使用 Bandai Namco ID（bnid.net）进行 OAuth 登录。
由于该站有较强的机器人检测（会跳转到 restriction 页面），
推荐使用 session 持久化方式首次手动登录，之后自动抓取。

登录流程：
  1. 访问 https://p-bandai.jp/
  2. 点击右上角「ログイン」
  3. 跳转到 bnid.net 登录页
  4. 填写邮箱 + 密码

订单历史页：
  URL: https://p-bandai.jp/my/order/

如果选择器不对，请在 config.yaml 的 bandai 下面调整：
  bandai:
    username: your@email.com
    password: your_password
    selectors:
      email_input: "#loginId"
      password_input: "#password"
      submit_button: ".login-btn"
      order_row: ".order-list__item"
      order_id: ".order-number"
      order_date: ".order-date"
      item_name: ".item-name"
      total_price: ".total-price"
"""
import re
from datetime import datetime

from playwright.async_api import Page, PlaywrightTimeoutError

from db.db import insert_many
from db.models import Purchase
from ingest.scraper_base import ShopScraper


class BandaiScraper(ShopScraper):
    SITE_KEY = "bandai"
    LOGIN_URL = "https://p-bandai.jp/"
    ORDER_HISTORY_URL = "https://p-bandai.jp/my/order/"
    LOGGED_IN_SELECTOR = ".mypage-menu, .user-info, [class*='logout'], [class*='mypage']"

    # Bandai Namco ID OAuth 登录页（实际跳转目标）
    BNID_LOGIN_URL = "https://account.bandai.com/login"

    def _sel(self, key: str, default: str) -> str:
        return self.site_config.get("selectors", {}).get(key, default)

    async def _is_logged_in(self, page: Page) -> bool:
        """检查是否已登录（在订单历史页上有内容，没有被重定向到登录页）"""
        current_url = page.url
        # 被重定向到 restriction 或 login，说明未登录
        if any(k in current_url.lower() for k in ["restriction", "login", "bnid.net", "account.bandai.com"]):
            return False
        # 检查订单历史页是否有内容
        if "my/order" in current_url:
            content = await page.content()
            # 如果页面有订单相关内容
            if any(k in content for k in ["注文番号", "注文履歴", "ご注文"]):
                return True
        # 检查 mypage 相关元素
        for sel in [".mypage-menu", ".user-menu", "[class*='mypage']", "text=ログアウト"]:
            try:
                el = await page.query_selector(sel)
                if el and await el.is_visible():
                    return True
            except Exception:
                continue
        return False

    async def _auto_login(self, page: Page) -> bool:
        """
        Premium Bandai 登录流程：
        1. 访问首页，点击登录按钮
        2. 跳转到 Bandai Namco ID 登录页（account.bandai.com 或 bnid.net）
        3. 填写邮箱 + 密码
        4. 等待跳回 p-bandai.jp
        """
        if not self.username or not self.password:
            return False

        try:
            print("[bandai] 访问首页，寻找登录入口...")
            await page.goto("https://p-bandai.jp/", wait_until="domcontentloaded", timeout=30000)
            await page.wait_for_timeout(2000)

            # 如果被 restriction 页面拦截，等待一下再试
            if "restriction" in page.url:
                print("[bandai] 遇到机器人检测页面，等待 5 秒后重试...")
                await page.wait_for_timeout(5000)
                await page.goto("https://p-bandai.jp/", wait_until="domcontentloaded", timeout=30000)

            # 点击登录按钮（各种可能的选择器）
            login_btn_selectors = [
                "text=ログイン",
                "a[href*='login']",
                ".login-btn",
                ".header-login",
                "[data-cy='login']",
                "button:has-text('ログイン')",
                ".sp-login",
            ]
            for sel in login_btn_selectors:
                try:
                    el = await page.wait_for_selector(sel, timeout=3000)
                    if el and await el.is_visible():
                        await el.click()
                        await page.wait_for_timeout(3000)
                        print(f"[bandai] 点击登录按钮: {sel}")
                        break
                except PlaywrightTimeoutError:
                    continue

            # 等待跳转到 Bandai Namco ID 登录页
            for _ in range(10):
                if any(k in page.url for k in ["account.bandai.com", "bnid.net", "login"]):
                    break
                await page.wait_for_timeout(1000)

            print(f"[bandai] 当前 URL: {page.url}")

            # 填写邮箱（ID 字段）
            email_sel = self._sel("email_input", "#loginId, #email, input[name='email'], input[type='email']")
            password_sel = self._sel("password_input", "#password, input[type='password'], input[name='password']")
            submit_sel = self._sel("submit_button", "button[type='submit'], .login-btn, .btn-login, input[type='submit']")

            await page.wait_for_selector(email_sel, timeout=10000)
            await page.fill(email_sel, self.username)
            await page.wait_for_timeout(500)

            await page.fill(password_sel, self.password)
            await page.wait_for_timeout(500)

            await page.click(submit_sel)

            # 等待跳回 p-bandai.jp
            print("[bandai] 等待登录完成...")
            for _ in range(15):
                await page.wait_for_timeout(2000)
                if "p-bandai.jp" in page.url and "login" not in page.url.lower():
                    print("[bandai] 自动登录成功")
                    return True

            return False

        except PlaywrightTimeoutError as e:
            print(f"[bandai] 自动登录超时: {e}")
            return False
        except Exception as e:
            print(f"[bandai] 自动登录异常: {e}")
            return False

    async def parse_orders(
        self,
        page: Page,
        date_from: str | None = None,
        date_to: str | None = None,
    ) -> list[dict]:
        """
        解析 Premium Bandai 订单历史页，支持翻页
        """
        all_purchases = []
        page_num = 0

        while True:
            page_num += 1
            print(f"[bandai] 解析第 {page_num} 页...")
            await page.wait_for_timeout(1500)

            # 等待订单内容加载
            try:
                await page.wait_for_selector(
                    ".order-list, .order-history, [class*='order-item'], table tr",
                    timeout=10000,
                )
            except PlaywrightTimeoutError:
                print(f"[bandai] 第 {page_num} 页未找到订单元素")
                break

            # 确定订单行选择器
            order_row_sel = self._sel("order_row", None)
            if not order_row_sel:
                for try_sel in [
                    ".order-list__item",
                    ".order-item",
                    ".order-history-item",
                    "li.order",
                    "[class*='order-list'] li",
                    "table.order tbody tr",
                    "[class*='orderItem']",
                ]:
                    rows = await page.query_selector_all(try_sel)
                    if rows:
                        order_row_sel = try_sel
                        print(f"[bandai] 使用订单行选择器: {try_sel}")
                        break

            if not order_row_sel:
                print("[bandai] 未找到订单行，尝试从文本提取...")
                purchases = await self._extract_from_text(page, date_from, date_to)
                all_purchases.extend(purchases)
                break

            rows = await page.query_selector_all(order_row_sel)
            if not rows:
                print(f"[bandai] 第 {page_num} 页没有订单行")
                break

            print(f"[bandai] 第 {page_num} 页找到 {len(rows)} 条订单")
            for row in rows:
                purchase = await self._parse_order_row(row)
                if purchase:
                    order_date = purchase.get("purchase_date", "")
                    if date_from and order_date and order_date < date_from:
                        continue
                    if date_to and order_date and order_date > date_to:
                        continue
                    all_purchases.append(purchase)

            # 翻页
            next_sel = self._sel("next_page", "a[rel='next'], .next-page, button.next, text=次のページ, text=次へ, .pagination__next")
            has_next = await self._navigate_next_page(page, next_sel)
            if not has_next:
                break

        return all_purchases

    async def _parse_order_row(self, row) -> dict | None:
        """从 Premium Bandai 订单行元素提取数据"""
        try:
            row_text = await row.text_content() or ""

            # 订单号
            order_id = ""
            order_id_sel = self._sel("order_id", "[class*='order-num'], [class*='order-id'], [class*='orderNumber']")
            try:
                id_el = await row.query_selector(order_id_sel)
                if id_el:
                    order_id = (await id_el.text_content() or "").strip()
            except Exception:
                pass
            if not order_id:
                m = re.search(r'(?:注文番号|Order[:\s#]*|No\.?\s*)[\s:：]*([0-9\-A-Z]+)', row_text, re.I)
                if m:
                    order_id = m.group(1)
            if not order_id:
                # 从纯数字中提取（日本电商订单号通常是纯数字）
                m = re.search(r'\b(\d{9,15})\b', row_text)
                if m:
                    order_id = m.group(1)

            if not order_id:
                return None

            # 日期
            order_date = ""
            date_sel = self._sel("order_date", "[class*='date'], time, [class*='Date']")
            try:
                date_el = await row.query_selector(date_sel)
                if date_el:
                    dt = await date_el.get_attribute("datetime")
                    order_date = self._parse_date(dt or await date_el.text_content() or "")
            except Exception:
                pass
            if not order_date:
                m = re.search(r'(\d{4})[年/\-](\d{1,2})[月/\-](\d{1,2})', row_text)
                if m:
                    order_date = f"{m.group(1)}-{m.group(2).zfill(2)}-{m.group(3).zfill(2)}"

            # 商品名
            item_name = ""
            name_sel = self._sel("item_name", "[class*='item-name'], [class*='product-name'], [class*='itemName']")
            try:
                name_el = await row.query_selector(name_sel)
                if name_el:
                    item_name = (await name_el.text_content() or "").strip()
            except Exception:
                pass

            # 价格
            total_price_jpy = None
            price_sel = self._sel("total_price", "[class*='price'], [class*='total'], [class*='amount'], [class*='Price']")
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
            quantity = 1
            qty_sel = self._sel("quantity", "[class*='qty'], [class*='quantity'], [class*='Qty']")
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
                id=f"bandai_{order_id}",
                platform="bandai",
                purchase_date=order_date or None,
                item_name=item_name or None,
                quantity=quantity,
                total_price_jpy=total_price_jpy,
                order_number=order_id,
            )
            return purchase.to_dict()

        except Exception as e:
            print(f"[bandai] 解析订单行异常: {e}")
            return None

    async def _extract_from_text(
        self,
        page: Page,
        date_from: str | None,
        date_to: str | None,
    ) -> list[dict]:
        """从页面文本提取订单信息（兜底方案）"""
        content = await page.content()
        purchases = []

        blocks = re.findall(
            r'(?:注文番号|ご注文番号|Order No\.?)[\s:：]+([0-9\-A-Z]+).*?'
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
                id=f"bandai_{order_id}",
                platform="bandai",
                purchase_date=order_date,
                total_price_jpy=float(price.replace(",", "")),
                order_number=order_id,
            )
            purchases.append(p.to_dict())

        return purchases

    def _parse_date(self, text: str) -> str:
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
        m = re.search(r'([0-9,]+)', text.replace("¥", "").replace("￥", "").strip())
        if m:
            return float(m.group(1).replace(",", ""))
        return None


def ingest_bandai(
    date_from: str | None = None,
    date_to: str | None = None,
    force_relogin: bool = False,
) -> int:
    """
    入口函数：抓取 Premium Bandai 订单并写入数据库

    Args:
        date_from: 开始日期 'YYYY-MM-DD'
        date_to:   结束日期 'YYYY-MM-DD'
        force_relogin: 强制重新登录

    Returns:
        实际插入的记录数
    """
    import asyncio

    scraper = BandaiScraper()
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
