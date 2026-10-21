"""审计反馈 P1 回归(P1-3 哈希噪声 / P1-4 盘口线同源 / P1-5 赔率基准 / P1-6 重试语义)。"""
from unittest import mock

from sources.bb import BBAdapter
from tests.helpers import nrec
from mapping.unified_db import save_unified, _content_hash


def _unified_record(**kw):
    """构造 save_unified 的输入(与 unify 内动态 UnifiedRecord 同构)。"""
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


def test_no_content_change_zero_events(db):
    """审计 P1-3 反向断言(审计点名盲区): 数据不变 5 轮 -> 0 个变化事件。"""
    for t in range(1, 6):
        _quote(db, received_at=t * 1000, odds=1.90)
    db.commit()
    n = db.execute(
        "SELECT count(*) FROM events WHERE event_type='quote_changed'"
    ).fetchone()[0]
    assert n == 0, "赔率不变不应产生变化事件, 实际 %d 个" % n


def test_content_change_emits_once(db):
    """内容真正变化时恰好 1 个 quote_changed。"""
    _quote(db, received_at=1000, odds=1.90)
    _quote(db, received_at=2000, odds=1.95)
    db.commit()
    n = db.execute(
        "SELECT count(*) FROM events WHERE event_type='quote_changed'"
    ).fetchone()[0]
    assert n == 1


def test_content_hash_stable_across_received_at():
    """哈希输入不含 received_at: 同内容不同轮哈希相同。"""
    a = nrec("bb", "m1", "mm1", "1000", "0.5", "主队-0.5", 1.90, 111)
    b = nrec("bb", "m1", "mm1", "1000", "0.5", "主队-0.5", 1.90, 222)
    assert _content_hash(a, "cid1") == _content_hash(b, "cid1")


def test_bb_line_same_source_as_line_raw():
    """审计 P1-4: op.li=0.75 / mk.li=0.5 -> line=0.75 且 line_raw='0.75'。"""
    ad = BBAdapter()
    match = {
        "id": 99, "lg": {"id": 11140}, "ts": [{"na": "MU"}, {"na": "CHE"}],
        "bt": "1700000000",
        "mg": [{"mty": "1000", "pe": "0", "mks": [
            {"id": "m1", "li": 0.5, "op": [
                {"na": "主队-0.5", "li": 0.75, "od": "1.90"},
            ]},
        ]}],
    }
    recs = ad.normalize(match, received_at=1000)
    assert len(recs) == 1
    assert recs[0].line == 0.75
    assert recs[0].line_raw == "0.75"


def test_bb_line_fallback_to_market_line():
    """op.li 缺失时回退盘口级 li, line 与 line_raw 仍同源。"""
    ad = BBAdapter()
    match = {
        "id": 99, "lg": {"id": 11140}, "ts": [{"na": "MU"}, {"na": "CHE"}],
        "bt": "1700000000",
        "mg": [{"mty": "1000", "pe": "0", "mks": [
            {"id": "m1", "li": -0.5, "op": [
                {"na": "主队-0.5", "od": "1.90"},
            ]},
        ]}],
    }
    recs = ad.normalize(match, received_at=1000)
    assert len(recs) == 1
    assert recs[0].line == -0.5
    assert recs[0].line_raw == "-0.5"


def test_bb_auth_error_no_retry():
    """审计 P1-6: 401(AUTH 不可重试) 只发 1 次请求即失败, 不空转重试。"""
    import requests
    ad = BBAdapter()

    def boom(*a, **k):
        resp = requests.models.Response()
        resp.status_code = 401
        raise requests.HTTPError("401 Unauthorized", response=resp)

    with mock.patch.object(ad.session, "post", side_effect=boom) as m:
        j, n = ad._get_page_with_retries(1, 3)
        assert j is None
        assert m.call_count == 1, "AUTH 不可重试应只请求 1 次, 实际 %d" % m.call_count


def test_bb_retryable_still_retries_then_succeeds():
    """500(RETRYABLE) 重试后成功: 重试语义不被误伤。"""
    import requests
    ad = BBAdapter()
    calls = {"n": 0}

    def flaky(*a, **k):
        calls["n"] += 1
        if calls["n"] == 1:
            resp = requests.models.Response()
            resp.status_code = 500
            raise requests.HTTPError("500", response=resp)
        return mock.Mock(json=lambda: {"success": True}, raise_for_status=lambda: None)

    with mock.patch.object(ad.session, "post", side_effect=flaky):
        j, n = ad._get_page_with_retries(1, 3)
        assert j is not None
        assert n == 1  # 重试 1 次后成功
