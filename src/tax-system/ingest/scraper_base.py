"""
ingest/scraper_base.py — Playwright 爬虫基类

设计思路：会话持久化（Session Persistence）
- 第一次运行时打开可见浏览器，让用户手动登录
- 登录成功后保存 cookie/session 到本地文件
- 之后自动重用 session，无需再次登录
- 支持账号密码自动登录（适用于没有验证码的情况）

这样可以：
✓ 支持二步验证 / 图形验证码（用户手动处理）
✓ 不用在代码里存密码明文
✓ Session 通常有效数周至数月
"""
import asyncio
import json
import os
import time
from pathlib import Path
from typing import Any

import yaml
from playwright.async_api import (
    Page,
    BrowserContext,
    async_playwright,
    TimeoutError as PlaywrightTimeoutError,
)

CONFIG_PATH = Path(__file__).parent.parent / "config.yaml"
SESSION_DIR = Path(__file__).parent.parent / "data" / "sessions"


def load_config() -> dict:
    if CONFIG_PATH.exists():
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    return {}


class ShopScraper:
    """
    日本购物网站爬虫基类

    子类需要实现：
    - SITE_KEY: str           config.yaml 中的配置键名
    - LOGIN_URL: str          登录页 URL
    - ORDER_HISTORY_URL: str  订单历史页 URL
    - LOGGED_IN_SELECTOR: str 已登录状态的 CSS 选择器（用于检测是否已登录）
    - login(page): 执行登录操作（填写表单、点击按钮等）
    - parse_orders(page): 解析订单历史页面，返回 Purchase 列表
    """

    SITE_KEY: str = "base"
    LOGIN_URL: str = ""
    ORDER_HISTORY_URL: str = ""
    LOGGED_IN_SELECTOR: str = ""        # 登录后才会出现的元素
    ORDER_HISTORY_URL_PATTERN: str = "" # 也用于判断是否跳到了登录页

    def __init__(self):
        self.config = load_config()
        self.site_config = self.config.get(self.SITE_KEY, {})
        self.session_file = SESSION_DIR / f"{self.SITE_KEY}_session.json"
        SESSION_DIR.mkdir(parents=True, exist_ok=True)

    @property
    def username(self) -> str:
        return self.site_config.get("username", "")

    @property
    def password(self) -> str:
        return self.site_config.get("password", "")

    def _session_exists(self) -> bool:
        """检查 session 文件是否存在且未过期（7天内）"""
        if not self.session_file.exists():
            return False
        age_days = (time.time() - self.session_file.stat().st_mtime) / 86400
        return age_days < 7

    def _clear_session(self) -> None:
        """删除过期 session，触发重新登录"""
        if self.session_file.exists():
            self.session_file.unlink()
            print(f"[scraper] {self.SITE_KEY}: session 已清除，下次运行需重新登录")

    async def _make_context(self, playwright, headless: bool = True) -> BrowserContext:
        """创建浏览器 context，加载已保存的 session（如果存在）"""
        browser = await playwright.chromium.launch(
            headless=headless,
            args=["--no-sandbox", "--disable-blink-features=AutomationControlled"],
        )
        context_kwargs = {
            "user_agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
            "locale": "ja-JP",
            "viewport": {"width": 1280, "height": 800},
            "extra_http_headers": {
                "Accept-Language": "ja-JP,ja;q=0.9,en;q=0.8",
            },
        }

        if self.session_file.exists():
            context_kwargs["storage_state"] = str(self.session_file)

        context = await browser.new_context(**context_kwargs)
        return context

    async def _save_session(self, context: BrowserContext) -> None:
        """保存当前 session 到文件"""
        await context.storage_state(path=str(self.session_file))
        print(f"[scraper] {self.SITE_KEY}: session 已保存 → {self.session_file}")

    async def _is_logged_in(self, page: Page) -> bool:
        """检查是否已登录（通过检查特定元素是否存在）"""
        if not self.LOGGED_IN_SELECTOR:
            # 通过 URL 判断是否被重定向到登录页
            return "login" not in page.url.lower()
        try:
            await page.wait_for_selector(self.LOGGED_IN_SELECTOR, timeout=3000)
            return True
        except PlaywrightTimeoutError:
            return False

    async def _auto_login(self, page: Page) -> bool:
        """
        尝试自动填写表单登录。
        子类覆盖此方法实现具体的登录流程。
        Returns True 表示登录成功（或已经登录）。
        """
        raise NotImplementedError

    async def _manual_login_wait(self, page: Page) -> bool:
        """
        打开浏览器让用户手动登录，等待登录成功。
        Returns True 表示用户完成了登录。
        """
        print(f"\n[scraper] {self.SITE_KEY}: 请在浏览器中手动登录...")
        print(f"[scraper] 登录页面：{self.LOGIN_URL}")
        print("[scraper] 登录成功后请等待，系统会自动检测并继续...\n")

        await page.goto(self.LOGIN_URL, wait_until="domcontentloaded", timeout=30000)

        # 等待用户登录，最多等 3 分钟
        max_wait = 180
        start = time.time()
        while time.time() - start < max_wait:
            if await self._is_logged_in(page):
                print(f"[scraper] {self.SITE_KEY}: 检测到已登录")
                return True
            await asyncio.sleep(2)

        print(f"[scraper] {self.SITE_KEY}: 登录超时（{max_wait}秒）")
        return False

    async def scrape(
        self,
        date_from: str | None = None,
        date_to: str | None = None,
        force_relogin: bool = False,
        headless: bool = True,
    ) -> list[dict]:
        """
        主入口：登录并抓取订单历史

        Args:
            date_from:      开始日期 'YYYY-MM-DD'（None 表示不限制）
            date_to:        结束日期 'YYYY-MM-DD'（None 表示今天）
            force_relogin:  强制重新登录（清除 session）
            headless:       是否无头模式（第一次登录建议 False）

        Returns:
            list of Purchase.to_dict() 字典
        """
        if force_relogin:
            self._clear_session()

        async with async_playwright() as pw:
            # 有 session 用无头模式，没有 session 用有头模式（方便手动登录）
            use_headless = headless and self._session_exists()
            context = await self._make_context(pw, headless=use_headless)
            page = await context.new_page()

            try:
                # ── 1. 导航到订单历史页（用已有 session）──────────────────
                print(f"[scraper] {self.SITE_KEY}: 导航到订单历史...")
                await page.goto(self.ORDER_HISTORY_URL, wait_until="domcontentloaded", timeout=30000)
                await page.wait_for_timeout(1500)

                # ── 2. 检查是否需要登录 ────────────────────────────────────
                if not await self._is_logged_in(page):
                    print(f"[scraper] {self.SITE_KEY}: session 无效，尝试登录...")

                    # 先尝试自动登录
                    login_success = False
                    if self.username and self.password:
                        try:
                            login_success = await self._auto_login(page)
                        except Exception as e:
                            print(f"[scraper] 自动登录失败: {e}")

                    # 自动登录失败，换有头模式让用户手动登录
                    if not login_success:
                        await context.close()
                        context = await self._make_context(pw, headless=False)
                        page = await context.new_page()
                        login_success = await self._manual_login_wait(page)

                    if not login_success:
                        raise RuntimeError(f"{self.SITE_KEY}: 登录失败")

                    await self._save_session(context)

                    # 登录后重新导航到订单页
                    await page.goto(self.ORDER_HISTORY_URL, wait_until="domcontentloaded", timeout=30000)
                    await page.wait_for_timeout(1500)

                # ── 3. 解析订单 ────────────────────────────────────────────
                print(f"[scraper] {self.SITE_KEY}: 开始解析订单...")
                orders = await self.parse_orders(page, date_from=date_from, date_to=date_to)
                print(f"[scraper] {self.SITE_KEY}: 解析完成，共 {len(orders)} 条订单")
                return orders

            except Exception as e:
                print(f"[scraper] {self.SITE_KEY}: 错误 — {e}")
                raise
            finally:
                await context.close()

    async def parse_orders(
        self,
        page: Page,
        date_from: str | None = None,
        date_to: str | None = None,
    ) -> list[dict]:
        """子类实现：解析订单历史页，返回 Purchase dict 列表"""
        raise NotImplementedError

    # ── 工具函数 ───────────────────────────────────────────────────────────

    async def _safe_text(self, page: Page, selector: str, default: str = "") -> str:
        """安全获取元素文字，不存在时返回 default"""
        try:
            el = await page.query_selector(selector)
            return (await el.text_content() or "").strip() if el else default
        except Exception:
            return default

    async def _safe_attr(self, page: Page, selector: str, attr: str, default: str = "") -> str:
        """安全获取元素属性，不存在时返回 default"""
        try:
            el = await page.query_selector(selector)
            return (await el.get_attribute(attr) or "").strip() if el else default
        except Exception:
            return default

    async def _navigate_next_page(self, page: Page, next_selector: str) -> bool:
        """
        点击下一页按钮并等待导航完成。
        Returns True 如果成功翻页，False 如果没有下一页。
        """
        try:
            next_btn = await page.query_selector(next_selector)
            if not next_btn:
                return False
            is_disabled = await next_btn.get_attribute("disabled")
            if is_disabled:
                return False
            await next_btn.click()
            await page.wait_for_load_state("domcontentloaded")
            await page.wait_for_timeout(1000)
            return True
        except Exception:
            return False
