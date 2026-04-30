"""
core/utils/asin.py
ASIN 抽取与短链解析工具。
"""
import re
from typing import Optional

# 标准 Amazon ASIN: B0 开头 + 8 位字母数字
_ASIN_RE = re.compile(r"^B0[A-Z0-9]{8}$")
_URL_PATTERNS = [
    re.compile(r"/dp/([A-Z0-9]{10})"),
    re.compile(r"/gp/product/([A-Z0-9]{10})"),
    re.compile(r"/gp/aw/d/([A-Z0-9]{10})"),
]
_DEFAULT_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)


def extract_asin_from_url(url: str | None) -> Optional[str]:
    """从 Amazon URL 抽取 ASIN（不展开短链）。返回 10 位 ASIN 或 None。"""
    if not isinstance(url, str):
        return None
    for pat in _URL_PATTERNS:
        m = pat.search(url)
        if m:
            return m.group(1)
    return None


def is_short_link(url: str | None) -> bool:
    """是否是 amzn.asia 短链。"""
    return isinstance(url, str) and "amzn.asia" in url


def is_standard_asin(s: str | None) -> bool:
    """是否是标准 Amazon ASIN（B0XXXXXXXX）。"""
    return isinstance(s, str) and bool(_ASIN_RE.match(s))


def clean_amazon_csv_asin(s: str | None) -> Optional[str]:
    """Amazon CSV 里的 ASIN 是 ="B0XXXXX" 格式，剥外壳。"""
    if not isinstance(s, str):
        return s
    return s.strip().lstrip("=").strip('"')


def expand_short_link(url: str, *, timeout: float = 15.0, user_agent: str = None) -> Optional[str]:
    """展开 amzn.asia 短链，返回最终 URL。失败返回 None。"""
    import httpx

    headers = {"User-Agent": user_agent or _DEFAULT_UA}
    try:
        with httpx.Client(follow_redirects=False, timeout=timeout, headers=headers) as c:
            r = c.head(url)
            if r.status_code in (301, 302, 307, 308) and r.headers.get("location"):
                return r.headers["location"]
            # fallback: 某些短链 HEAD 不返回 location，改用 GET
            with httpx.Client(follow_redirects=True, timeout=timeout, headers=headers) as c2:
                return str(c2.get(url).url)
    except Exception:
        return None
