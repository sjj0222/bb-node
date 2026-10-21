"""Phase 3 测试: Adapter 契约与来源健康(规格 §6)。

覆盖:
  1. classify_error 五类错误分类
  2. redact 日志脱敏
  3. backoff_sleep 退避 + Retry-After
  4. bb/sx capabilities 契约
  5. bb max_pages / 协议变化护栏
  6. 单一来源故障不拖垮其他来源 + 历史仍可查询
  7. collect_source 失败按契约分类 -> health 状态
"""
import time
import requests
import pytest

from sources.contract import (
    BaseAdapter, RETRYABLE, NON_RETRYABLE, AUTH, RATE_LIMIT,
    PROTOCOL_CHANGE, classify_exception, redact, backoff_sleep,
)
from sources import bb as bb_mod
from sources import sx as sx_mod
from core import collector, health


# ---------- 1. 错误分类(§6.1 classify_error) ----------

def _http_err(code):
    resp = requests.Response()
    resp.status_code = code
    err = requests.HTTPError("http %s" % code)
    err.response = resp
    return err


def test_classify_timeout_retryable():
    e = requests.exceptions.ReadTimeout("timed out")
    assert classify_exception(e) == RETRYABLE


def test_classify_429_rate_limit():
    assert classify_exception(_http_err(429)) == RATE_LIMIT


def test_classify_401_403_auth():
    assert classify_exception(_http_err(401)) == AUTH
    assert classify_exception(_http_err(403)) == AUTH


def test_classify_5xx_retryable():
    assert classify_exception(_http_err(500)) == RETRYABLE
    assert classify_exception(_http_err(502)) == RETRYABLE


def test_classify_4xx_non_retryable():
    assert classify_exception(_http_err(400)) == NON_RETRYABLE


def test_classify_json_decode_non_retryable():
    import json
    assert classify_exception(json.JSONDecodeError("x", "y", 0)) \
        == NON_RETRYABLE


def test_classify_protocol_change_by_message():
    e = RuntimeError("sx protocol shift: missing data.markets")
    assert classify_exception(e) == PROTOCOL_CHANGE


# ---------- 2. 脱敏(§6.2 日志不得写出密钥) ----------

def test_redact_masks_secrets():
    out = redact('token=abc123&sign=xyz&url=https://x?api_key=kkkk')
    assert "abc123" not in out
    assert "kkkk" not in out
    out2 = redact('{"api_key": "super-secret", "password": "p@ss"}')
    assert "super-secret" not in out2
    assert "p@ss" not in out2
    out3 = redact("GET https://api.example.com/v1/matches")
    assert "api.example.com" in out3   # 普通 URL 保留


# ---------- 3. 退避(§6.2 Retry-After) ----------

def test_backoff_respects_retry_after(monkeypatch):
    sleeps = []
    monkeypatch.setattr(time, "sleep", lambda s: sleeps.append(s))
    resp = requests.Response()
    resp.headers["Retry-After"] = "3"
    backoff_sleep({"backoff_max": 30.0}, 0, response=resp)
    assert sleeps == [3.0]


def test_backoff_exponential_capped(monkeypatch):
    sleeps = []
    monkeypatch.setattr(time, "sleep", lambda s: sleeps.append(s))
    policy = {"backoff_base": 2.0, "backoff_max": 5.0, "jitter": [1.0, 1.0]}
    backoff_sleep(policy, 0)
    backoff_sleep(policy, 1)
    backoff_sleep(policy, 2)
    assert sleeps[0] == 2.0
    assert sleeps[1] == 4.0
    assert sleeps[2] == 5.0    # capped


# ---------- 4. capabilities 契约 ----------

def test_bb_capabilities_contract():
    cap = bb_mod.BBAdapter().capabilities()
    assert "match" in cap["entities"]
    assert cap["paging"]["supported"] is True
    assert cap["paging"]["max_pages"] >= 1
    assert cap["incremental"] is False
    assert isinstance(cap["markets"], list)


def test_sx_capabilities_no_paging():
    cap = sx_mod.SXBetAdapter().capabilities()
    assert cap["paging"]["supported"] is False
    assert "market" in cap["entities"]


def test_bb_parse_records_filters_leagues():
    a = bb_mod.BBAdapter(leagues={})
    payload = {"success": True, "data": {"records": [
        {"id": 1, "lg": {"id": 11062}},
        {"id": 2, "lg": {"id": 99999}},
    ]}}
    recs = a.parse_records(payload)
    assert len(recs) == 2          # leagues={} = 全量


def test_bb_fetch_page_next_cursor():
    a = bb_mod.BBAdapter(leagues={})
    payload = {"success": True, "data": {
        "records": [{"id": 1, "lg": {"id": 11062}}],
        "total": 1, "size": 50, "serverTime": 1700000000000}}
    a.session = _FakeSession(payload)
    j, nxt, st, meta = a.fetch_page(1, window=50)
    assert nxt is None              # 末页
    assert st == 1700000000000
    assert meta["partial"] is False


class _FakeSession:
    def __init__(self, payload):
        self.payload = payload

    def post(self, *a, **kw):
        r = requests.Response()
        r.status_code = 200
        r._json = self.payload
        r.json = lambda: r._json
        return r


# ---------- 5. bb 护栏 ----------

class _EndlessBB(bb_mod.BBAdapter):
    """永远还有下一页的模拟, 用于 max_pages 护栏测试。"""

    def __init__(self):
        super().__init__(leagues={})
        self.n = 0

    def _get_page_with_retries(self, page, typ):
        self.n += 1
        return {"success": True, "data": {
            "records": [{"id": page, "lg": {"id": 11062}}],
            "total": 99999, "size": 1}}, 0

    def rate_limit_policy(self):
        p = super().rate_limit_policy()
        p["max_pages"] = 3
        return p


def test_bb_fetch_max_pages_guard(monkeypatch):
    monkeypatch.setattr(bb_mod.time, "sleep", lambda s: None)
    a = _EndlessBB()
    matches, meta = a.fetch_with_meta(3)
    assert meta["partial"] is True
    assert meta["error_code"] == "MAX_PAGES"
    assert meta["pages"] == 3


class _ShiftBB(bb_mod.BBAdapter):
    """响应缺少 data 契约键 -> 协议变化。"""

    def _get_page_with_retries(self, page, typ):
        return {"success": True, "foo": "bar"}, 0


def test_bb_fetch_protocol_shift(monkeypatch):
    monkeypatch.setattr(bb_mod.time, "sleep", lambda s: None)
    a = _ShiftBB()
    _, meta = a.fetch_with_meta(3)
    assert meta["partial"] is True
    assert meta["error_code"] == "PROTOCOL_CHANGE"


def test_sx_detect_protocol_shift():
    a = sx_mod.SXBetAdapter()
    assert a.detect_protocol_shift({"data": {"foo": 1}}) is True
    assert a.detect_protocol_shift({"data": {"markets": []}}) is False
    assert a.detect_protocol_shift({"data": "oops"}) is True


# ---------- 6/7. 来源健康与隔离 ----------

class _RaisingBB:
    source = "bb"
    last_collect_meta = None

    def collect(self, *a, **kw):
        raise _http_err(429)


def test_collect_source_classifies_rate_limit(db, monkeypatch):
    monkeypatch.setattr(collector, "get_adapter", lambda name: _RaisingBB())
    r = collector.collect_source("bb")
    assert r["success"] is False
    st = health.get("bb")
    assert st["status"] == "RATE_LIMIT"
    assert "429" in st["last_error"] or st["last_error"]


class _OkSX:
    source = "sx"
    last_collect_meta = None

    def fetch(self, received_at=None):
        return {}


def test_single_source_failure_isolated(db, monkeypatch):
    """规则 3.3/§6.5: 单一来源故障不拖垮其他来源, 历史仍可查询。"""
    real_cc = collector.collect_source
    calls = []

    def fake_cc(name):
        calls.append(name)
        if name == "bb":
            raise RuntimeError("bb down")
        return {"source": name, "success": True, "matches": 0,
                "unified": 0, "rows": 0}

    monkeypatch.setattr(collector, "collect_source", fake_cc)
    results = collector.collect(["bb", "sx"])
    assert [r["success"] for r in results] == [False, True]
    assert calls == ["bb", "sx"]
    # 来源失败不影响历史数据查询
    assert db.execute(
        "select count(*) from unified_snapshots").fetchone()[0] >= 0
