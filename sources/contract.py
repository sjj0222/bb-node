"""Phase 3: 统一 Adapter 接口契约(规格 §6.1/6.2)。

所有来源实现同一套逻辑接口; 错误分类 / 指数退避 / 日志脱敏 /
协议变化检测由全部来源共用, 保证:
  - 单一来源故障不拖垮其他来源
  - 协议变化可检测(不静默按旧结构解析)
  - 真实请求遵守来源规则(限流/退避/Retry-After)
"""
import random
import re
import time

from core import env

# ---------- 错误分类(规格 §6.1 classify_error) ----------
RETRYABLE = "RETRYABLE"                # 网络抖动/5xx, 可重试
NON_RETRYABLE = "NON_RETRYABLE"        # 4xx/格式错误, 重试无意义
AUTH = "AUTH"                          # 401/403 认证失败
RATE_LIMIT = "RATE_LIMIT"              # 429 限流, 须遵守 Retry-After
PROTOCOL_CHANGE = "PROTOCOL_CHANGE"    # 响应结构不符合契约

_SENSITIVE_PARTS = (
    "token", "password", "passwd", "secret", "api_key", "apikey",
    "authorization", "cookie", "device-id", "credential", "sign",
)


def redact(text, sensitive=_SENSITIVE_PARTS):
    """日志脱敏: 敏感键的键值对( key=value / "key": "value" )打码。"""
    if not text:
        return text
    out = str(text)
    for key in sensitive:
        pat = re.compile(
            r'(?i)("?)' + re.escape(key) + r'("?)(\s*[=:]\s*)'
            r'(?:"?)([^,\s&"\'{}]+)(?:"?)')
        out = pat.sub(
            lambda m: '%s%s%s%s***' % (m.group(1), key, m.group(2),
                                       m.group(3)),
            out)
    return out


def classify_exception(error):
    """把异常/HTTP 响应分类到五类错误。

    error 可以是 requests 异常(含 .response)或带 status_code 的响应对象。
    """
    if error is None:
        return NON_RETRYABLE
    resp = getattr(error, "response", None)
    code = None
    if resp is not None and getattr(resp, "status_code", None):
        code = resp.status_code
    if code is None and hasattr(error, "status_code"):
        code = error.status_code

    if code is not None:
        if code == 429:
            return RATE_LIMIT
        if code in (401, 403):
            return AUTH
        if code >= 500:
            return RETRYABLE
        if 400 <= code < 500:
            return NON_RETRYABLE

    name = type(error).__name__
    msg = str(error)
    low = msg.lower()
    if any(k in low for k in ("rate limit", "too many requests",
                              "limit exceeded")):
        return RATE_LIMIT
    if any(k in low for k in ("401", "403", "unauthorized", "forbidden",
                              "auth")):
        return AUTH
    if any(k in low for k in ("protocol", "schema", "unexpected key",
                              "missing key")):
        return PROTOCOL_CHANGE
    if "timeout" in low or "timed out" in low or name in (
            "Timeout", "ConnectTimeout", "ReadTimeout", "ConnectionError"):
        return RETRYABLE
    if name in ("JSONDecodeError", "ValueError", "TypeError",
                "KeyError", "AttributeError"):
        return NON_RETRYABLE
    return RETRYABLE


def backoff_sleep(policy, attempt, response=None):
    """指数退避 + 随机抖动; 提供 429/503 响应时优先遵守 Retry-After。

    policy: {"backoff_base", "backoff_max", "jitter": [lo, hi]}
    """
    if response is not None:
        ra = response.headers.get("Retry-After") \
            if hasattr(response, "headers") else None
        if ra:
            try:
                wait = min(max(0.0, float(ra)),
                           float(policy.get("backoff_max", 30.0)))
                time.sleep(wait)
                return
            except (TypeError, ValueError):
                pass
    base = float(policy.get("backoff_base", 2.0))
    cap = float(policy.get("backoff_max", 20.0))
    lo, hi = policy.get("jitter", [0.5, 1.5])
    # P3-16: 抖动必须乘在 cap 之前——此前 min(base*2^n, cap)*jitter
    # 让退避突破上限(backoff_max=20 实际最长睡 30s)
    wait = min(base * (2 ** max(0, attempt)) * random.uniform(lo, hi), cap)
    time.sleep(wait)


class BaseAdapter:
    """规格 §6.1 Adapter 接口契约。

    适配器只负责来源通信和源字段解析; 不跨来源合并、不生成信号、不写 UI。
    """

    source = "unknown"
    bookmaker = None

    # ---------- 契约接口 ----------
    def source_code(self):
        return self.source

    def capabilities(self):
        raise NotImplementedError

    def health_check(self):
        raise NotImplementedError

    def fetch_page(self, cursor, window=50, limits=None):
        raise NotImplementedError

    def parse_records(self, payload):
        raise NotImplementedError

    def rate_limit_policy(self):
        raise NotImplementedError

    def classify_error(self, error):
        return classify_exception(error)

    # ---------- 共享工具 ----------
    def _policy(self, cfg_key, defaults):
        """按来源配置读取限流策略, 未配置用默认值。"""
        cfg = (env.get(cfg_key) or {}).get("policy") or {}
        d = dict(defaults)
        d.update(cfg)
        return d
