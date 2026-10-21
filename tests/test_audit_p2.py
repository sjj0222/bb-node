"""审计反馈 P2 回归(P2-7 rowid 误用 / P2-8 emit 偷 commit / P2-9 连接泄漏 /
P2-10 sx 盘口隔离 / P2-11 config timeout 生效)。"""
from unittest import mock

from core import collector
from event import engine as ev
from sources import sx as sx_mod
from sources.bb import BBAdapter
from sources.sx import SXBetAdapter, pct_to_decimal
from mapping.unified_db import save_unified


def _unified_record(**kw):
    base = dict(
        source="bb", bookmaker="BB", source_match_id="m1",
        source_market_id="mm1", market_type="1000", period="0",
        line_raw="0.5", line=0.5, line_quarters=None, side="HOME",
        option="主队-0.5", odds=1.90, odds_raw="1.90",
        event_time=1000, server_time=1000, received_at=1000,
        raw_ref="raw", league_id=None, pipeline_version="t")
    base.update(kw)
    return type("UnifiedRecord", (), base)()


def _quote(conn, received_at, odds, line=0.5):
    save_unified(_unified_record(received_at=received_at, odds=odds,
                                 line=line, line_raw=str(line)), "cid1",
                 conn=conn)


# ---- P2-7: last_insert_rowid 跨表误用 ----

def test_duplicate_ingest_no_extra_events(db):
    """重复采集(INSERT OR IGNORE 生效)不得误报事件。

    修复前: IGNORE 被忽略时 last_insert_rowid() 不更新, 残留其他表
    (market_mappings 等)的 rowid, prev 边界错乱 -> 重复采集随机误发。
    修复后: prev 在插入前按同 key 最近快照查询。
    """
    _quote(db, received_at=1000, odds=1.90)
    _quote(db, received_at=2000, odds=1.95)   # 真变化 -> 1 个事件
    _quote(db, received_at=2000, odds=1.95)   # 同轮重复 -> 应忽略, 不增事件
    db.commit()
    n = db.execute(
        "SELECT count(*) FROM events WHERE event_type='quote_changed'"
    ).fetchone()[0]
    assert n == 1, "重复摄入不应增加事件, 实际 %d" % n


# ---- P2-8: emit / iter_events 默认不 commit ----

def test_emit_default_no_commit(db):
    ev.emit(db, source="bb", event_type="x", entity_key="k", event_time=1)
    db.rollback()
    assert db.execute("SELECT count(*) FROM events").fetchone()[0] == 0
    ev.emit(db, source="bb", event_type="x", entity_key="k", event_time=2)
    db.commit()
    assert db.execute("SELECT count(*) FROM events").fetchone()[0] == 1


def test_iter_events_default_no_commit(db):
    ev.emit(db, source="bb", event_type="x", entity_key="k", event_time=1)
    db.commit()
    list(ev.iter_events(db, "consumer1"))
    db.rollback()
    n = db.execute(
        "SELECT count(*) FROM event_consumers WHERE consumer='consumer1'"
    ).fetchone()[0]
    assert n == 0, "iter_events 默认不应逐行 commit, 回滚后标记应消失"


def test_shared_conn_batch_atomicity(db):
    """collector 共享连接批量写: 事件不中途提交, rollback 后行与事件都不在。"""
    _quote(db, received_at=1000, odds=1.90)
    _quote(db, received_at=2000, odds=1.95)
    ev.emit(db, source="bb", event_type="quote_changed", entity_key="k",
            event_time=2000)
    db.rollback()
    assert db.execute("SELECT count(*) FROM events").fetchone()[0] == 0
    assert db.execute(
        "SELECT count(*) FROM unified_snapshots").fetchone()[0] == 0


# ---- P2-9: 采集异常路径连接必须关闭 ----

def test_collect_source_exception_closes_conn(monkeypatch, db):
    """异常路径: rollback + close 全部打开的连接(修复前每轮泄漏一个)。"""
    real_connect = collector.connect
    opened, closed = [], []

    def tracking(*a, **k):
        c = real_connect(*a, **k)
        wrapped = mock.Mock(wraps=c)
        wrapped.close = mock.Mock(side_effect=c.close)
        opened.append(wrapped)
        closed.append(wrapped)  # 反向断言: 由 test 检查是否全部 close
        return wrapped

    monkeypatch.setattr(collector, "connect", tracking)

    class BoomAdapter:
        source = "bb"

        def collect(self, *a, **k):
            raise RuntimeError("source boom")

    monkeypatch.setattr(
        collector, "get_adapter", lambda name: BoomAdapter())

    result = collector.collect_source("bb")
    assert result["success"] is False
    assert opened, "应打开过连接"
    unclosed = [c for c in opened if c.close.call_count == 0]
    assert not unclosed, "泄漏 %d 个连接(未 close)" % len(unclosed)


# ---- P2-10: sx 单盘口失败隔离 + 重试 + partial ----

def test_sx_single_market_failure_is_partial(monkeypatch):
    """单盘口失败只跳过该盘口(partial 降级), 不整源归零。"""
    ad = SXBetAdapter()
    ad.session = mock.Mock()
    markets = [
        {"sportXeventId": 1, "type": 3, "line": -0.5,
         "marketHash": "h1", "mainLine": True},
        {"sportXeventId": 1, "type": 3, "line": -0.5,
         "marketHash": "h2", "mainLine": False},
    ]
    ad.fetch_markets = mock.Mock(return_value=markets)
    real_get = sx_mod.env.get

    def no_interval(path, default=None):
        if path == "sources.sx.request_interval_ms":
            return 0
        return real_get(path, default)

    monkeypatch.setattr(sx_mod.env, "get", no_interval)
    calls = {"n": 0}

    def odds(h):
        calls["n"] += 1
        if h == "h2":
            raise RuntimeError("orderbook boom")
        return {"outcomeOne": [{"percentageOdds": "50000000000000000000"}]}

    ad.fetch_odds = mock.Mock(side_effect=odds)

    out = ad.fetch(received_at=1000)
    assert calls["n"] == 2           # 两个盘口都尝试
    assert len(out) == 1             # 只有 h1 产出
    assert out[1][0]["market"]["marketHash"] == "h1"
    assert ad.last_collect_meta["partial"] is True
    assert ad.last_collect_meta["error_code"] == "ODDS_PARTIAL"


def test_sx_fetch_odds_retries_then_succeeds():
    """fetch_odds 与 fetch_markets 对齐的退避重试: 500 后成功。"""
    import requests
    ad = SXBetAdapter()
    ad.session = mock.Mock()
    calls = {"n": 0}

    def flaky(*a, **k):
        calls["n"] += 1
        if calls["n"] == 1:
            resp = requests.models.Response()
            resp.status_code = 500
            raise requests.HTTPError("500", response=resp)
        return mock.Mock(json=lambda: {"status": "success", "data": {"x": 1}},
                         raise_for_status=lambda: None)

    ad.session.get = flaky
    d = ad.fetch_odds("h1")
    assert d == {"x": 1}
    assert calls["n"] == 2


# ---- P2-11: config timeout 生效 ----

def test_bb_timeout_reads_config(monkeypatch):
    real_get = sx_mod.env.get
    monkeypatch.setattr(
        sx_mod.env, "get",
        lambda path, default=None: {"timeout": 33}
        if path == "sources.bb" else real_get(path, default))
    assert BBAdapter().timeout == 33


def test_sx_timeout_reads_config(monkeypatch):
    real_get = sx_mod.env.get
    monkeypatch.setattr(
        sx_mod.env, "get",
        lambda path, default=None: {"timeout": 44}
        if path == "sources.sx" else real_get(path, default))
    assert SXBetAdapter().timeout == 44
