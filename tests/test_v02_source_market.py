"""V0.2 测试矩阵 1: Source Health + Market Plugin(规则 67/70)。

覆盖: Source 状态记录/HTTP vs DATA success/STALE; Market handler 路由
(AH/Total/1X2/UNSUPPORTED/INVALID)、插件注册覆盖。
"""
import time

import pytest

from core import health
from market.registry import (REGISTRY, get_handler, MarketHandler,
                             AHHandler, TotalHandler, MatchResultHandler,
                             UnsupportedHandler)


class _FakeHandler(MarketHandler):
    name = "fake"
    requires_line = False


def test_health_unknown_before_record():
    assert health.status_of("ghost") == health.UNKNOWN


def test_health_record_ok(db):
    health.record("bb", status=health.UP, latency_ms=120, records=5,
                  http_ok=True, data_ok=True, pipeline_ok=True)
    h = health.get("bb")
    assert h["status"] == health.UP
    assert h["http_success"] == 1
    assert h["data_success"] == 1
    assert h["pipeline_success"] == 1


def test_health_http_ok_data_bad(db):
    # 规则 14: HTTP 200 不代表数据有效
    health.record("sx", status=health.INVALID_RESPONSE, latency_ms=80,
                  records=0, error="empty body",
                  http_ok=True, data_ok=False, pipeline_ok=False)
    h = health.get("sx")
    assert h["status"] == health.INVALID_RESPONSE
    assert h["http_success"] == 1
    assert h["data_success"] == 0
    assert h["error_count"] == 1


def test_health_error_count_accumulates(db):
    health.record("bb", status=health.DOWN, error="timeout")
    health.record("bb", status=health.DOWN, error="timeout again")
    assert health.get("bb")["error_count"] == 2


def test_health_stale(db):
    health.record("bb", status=health.UP)
    # 伪造 last_success 为很久以前
    import sqlite3 as _sqlite3
    c = _sqlite3.connect(__import__("os").environ["BB_NODE_DB"])
    old = int(time.time() * 1000) - 99999999
    c.execute("update source_health set last_success=?", (old,))
    c.commit()
    c.close()
    assert health.status_of("bb", stale_after_seconds=60) == health.STALE


def test_market_registry_defaults(db):
    assert isinstance(get_handler("asian_handicap"), AHHandler)
    assert isinstance(get_handler("total"), TotalHandler)
    assert isinstance(get_handler("1x2"), MatchResultHandler)


def test_market_unsupported_handler(db):
    h = get_handler("no_such_market_xyz")
    assert isinstance(h, UnsupportedHandler)
    status, line, side = h.normalize(None, "no_such_market_xyz")
    assert status == "UNSUPPORTED"


def test_market_plugin_register_overrides(db):
    REGISTRY.register("asian_handicap", _FakeHandler())
    try:
        assert isinstance(get_handler("asian_handicap"), _FakeHandler)
    finally:
        # 恢复默认 AH handler
        REGISTRY._handlers["asian_handicap"] = AHHandler()


def test_market_registry_list(db):
    lst = REGISTRY.list()
    assert "asian_handicap" in lst
    assert "corner_over_under" in lst  # 真实数据已有市场不丢
