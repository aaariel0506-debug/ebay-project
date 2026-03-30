"""
ingest/exchange_rate.py — 从 Frankfurter API 获取 JPY/USD 历史汇率

用法：
    from ingest.exchange_rate import get_rate_jpy_usd, batch_get_rates
    
    rate = get_rate_jpy_usd('2026-02-15')  # 返回 0.006541 (约 1/152.87)
    rates = batch_get_rates(['2026-02-01', '2026-02-15', '2026-02-28'])
"""
import requests
from datetime import datetime, timedelta
from typing import Optional
import yaml
import os

# 模块级缓存：{date_str: rate}
_rate_cache: dict[str, float] = {}

# 默认 fallback 值（1 USD = 150 JPY → 1 JPY = 1/150 USD）
DEFAULT_FALLBACK = 1 / 150.0


def _get_fallback_rate() -> float:
    """
    从 config.yaml 读取 exchange_rate.fallback_jpy_usd。
    若 config 不存在或字段缺失，返回默认值 1/150。
    """
    config_paths = [
        'config.yaml',
        os.path.join(os.path.dirname(os.path.dirname(__file__)), 'config.yaml'),
    ]
    
    for path in config_paths:
        if os.path.exists(path):
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    config = yaml.safe_load(f)
                if config and 'exchange_rate' in config:
                    fallback = config['exchange_rate'].get('fallback_jpy_usd')
                    if fallback is not None and fallback > 0:
                        return 1.0 / fallback
            except Exception:
                pass
    
    return DEFAULT_FALLBACK


def _cache_key(date: str) -> str:
    """标准化日期格式为 YYYY-MM-DD"""
    return date


def _find_nearest_rate(date: str, rates_dict: dict[str, dict]) -> Optional[float]:
    """
    在已获取的 rates_dict 中查找 date 的汇率。
    若 date 不在 dict 中（周末/节假日），向前查找最近的工作日。
    最多回溯 7 天，超过则返回 None。
    
    Args:
        date: 'YYYY-MM-DD' 格式
        rates_dict: Frankfurter API 返回的 rates 字典 {date: {currency: rate}}
    
    Returns:
        JPY/USD 汇率（1 JPY = ? USD），找不到则返回 None
    """
    try:
        target_date = datetime.strptime(date, '%Y-%m-%d')
    except ValueError:
        return None
    
    # 最多回溯 7 天
    for days_back in range(8):
        check_date = target_date - timedelta(days=days_back)
        check_date_str = check_date.strftime('%Y-%m-%d')
        
        if check_date_str in rates_dict:
            jpy_rate = rates_dict[check_date_str].get('JPY')
            if jpy_rate and jpy_rate > 0:
                # API 返回 1 USD = X JPY，转换为 1 JPY = Y USD
                return 1.0 / jpy_rate
    
    return None


def _fetch_rates_for_range(start_date: str, end_date: str) -> Optional[dict]:
    """
    从 Frankfurter API 获取日期区间的汇率。
    
    Returns:
        API 响应字典，失败则返回 None
    """
    url = f"https://api.frankfurter.app/{start_date}..{end_date}?from=USD&to=JPY"
    
    try:
        response = requests.get(url, timeout=5)
        if response.status_code == 200:
            return response.json()
        else:
            print(f"⚠ 汇率 API 返回非 200 状态码：{response.status_code}")
            return None
    except requests.Timeout:
        print("⚠ 汇率获取超时（>5 秒），使用备用值")
        return None
    except requests.ConnectionError:
        print("⚠ 汇率获取失败（网络错误），使用备用值")
        return None
    except Exception as e:
        print(f"⚠ 汇率获取失败：{e}，使用备用值")
        return None


def _get_month_range(date: str) -> tuple[str, str]:
    """获取日期所在月份的第一天和最后一天"""
    try:
        dt = datetime.strptime(date, '%Y-%m-%d')
        start = dt.replace(day=1).strftime('%Y-%m-%d')
        
        # 计算月末
        if dt.month == 12:
            next_month = dt.replace(year=dt.year + 1, month=1, day=1)
        else:
            next_month = dt.replace(month=dt.month + 1, day=1)
        end = (next_month - timedelta(days=1)).strftime('%Y-%m-%d')
        
        return start, end
    except ValueError:
        return date, date


def get_rate_jpy_usd(date: str) -> float:
    """
    获取指定日期的 JPY→USD 汇率（1 JPY 换多少 USD）。
    
    参数：
        date: 'YYYY-MM-DD' 格式日期字符串
    
    返回：
        float，如 0.00667（约等于 1/150）
    
    异常：
        网络失败时返回 fallback 值并打印警告，不抛异常
    """
    cache_key = _cache_key(date)
    
    # 检查缓存
    if cache_key in _rate_cache:
        return _rate_cache[cache_key]
    
    # 获取该月范围的汇率
    start, end = _get_month_range(date)
    data = _fetch_rates_for_range(start, end)
    
    if data and 'rates' in data:
        rates_dict = data['rates']
        rate = _find_nearest_rate(date, rates_dict)
        if rate is not None:
            _rate_cache[cache_key] = rate
            return rate
    
    # Fallback
    fallback = _get_fallback_rate()
    _rate_cache[cache_key] = fallback
    return fallback


def get_usd_per_jpy(date: str) -> float:
    """get_rate_jpy_usd 的别名，语义更清晰"""
    return get_rate_jpy_usd(date)


def batch_get_rates(dates: list[str]) -> dict[str, float]:
    """
    批量获取多个日期的汇率，减少 HTTP 请求次数。
    
    策略：
    1. 按月份分组，一次请求拉取整月范围
    2. 周末/节假日取最近一个工作日的汇率
    3. 结果缓存到内存（进程生命周期内）
    
    返回：
        dict，key 为 'YYYY-MM-DD'，value 为 float
    """
    if not dates:
        return {}
    
    # 按月份分组
    month_groups: dict[str, list[str]] = {}
    for date in dates:
        try:
            dt = datetime.strptime(date, '%Y-%m-%d')
            month_key = date[:7]  # 'YYYY-MM'
            if month_key not in month_groups:
                month_groups[month_key] = []
            month_groups[month_key].append(date)
        except ValueError:
            continue
    
    result: dict[str, float] = {}
    
    for month_key, month_dates in month_groups.items():
        # 检查缓存
        cached = {d: _rate_cache.get(_cache_key(d)) for d in month_dates if _cache_key(d) in _rate_cache}
        uncached = [d for d in month_dates if _cache_key(d) not in cached]
        
        result.update({k: v for k, v in cached.items() if v is not None})
        
        if not uncached:
            continue
        
        # 获取该月的汇率范围
        start = f"{month_key}-01"
        dt = datetime.strptime(start, '%Y-%m-%d')
        if dt.month == 12:
            next_month = dt.replace(year=dt.year + 1, month=1, day=1)
        else:
            next_month = dt.replace(month=dt.month + 1, day=1)
        end = (next_month - timedelta(days=1)).strftime('%Y-%m-%d')
        
        data = _fetch_rates_for_range(start, end)
        
        if data and 'rates' in data:
            rates_dict = data['rates']
            for date in uncached:
                cache_key = _cache_key(date)
                rate = _find_nearest_rate(date, rates_dict)
                if rate is not None:
                    _rate_cache[cache_key] = rate
                    result[date] = rate
                else:
                    fallback = _get_fallback_rate()
                    _rate_cache[cache_key] = fallback
                    result[date] = fallback
        else:
            # API 失败，全部使用 fallback
            fallback = _get_fallback_rate()
            for date in uncached:
                cache_key = _cache_key(date)
                _rate_cache[cache_key] = fallback
                result[date] = fallback
    
    return result


def clear_cache():
    """清除缓存（用于测试）"""
    _rate_cache.clear()
