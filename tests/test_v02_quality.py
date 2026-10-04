"""V0.2 测试矩阵 2: Data Quality(规则 71)。

覆盖: missing / invalid / duplicate / stale / conflict / unmapped /
out-of-order + score 与显式状态并存。
"""
import time
import sqlite3

import pytest

from quality import engine_v1 as dq


def _seed(conn, rows):
    for r in rows:
        conn.execute("""insert into unified_snapshots(
            canonical_match_id,source,bookmaker,source_match_id,
            source_market_id,market_type,period,line_raw,line,side,
            option,odds,event_time,server_time,received_at,raw_ref,
            pipeline_version,created_at)
            values(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (r.get("canonical_match_id", "cm1"), r["source"], r["source"],
             r["source_match_id"], r["source_market_id"], r["market_type"],
             r.get("period", "full_time"), r.get("line_raw"),
             r.get("line"), r.get("side", "HOME"), r["option"],
             r["odds"], r.get("event_time", 1000),
             r.get("server_time", 1000), r["received_at"],
             r.get("raw_ref", "raw-x"), "0.2.0", int(time.time() * 1000)))
    conn.commit()


def _base(source="bb", smid="m1", mmid="mm1", option="主队-0.5", odds=1.9,
          received_at=1000, **kw):
    r = dict(source=source, source_match_id=smid, source_market_id=mmid,
             market_type="asian_handicap", option=option, odds=odds,
             received_at=received_at)
    r.update(kw)
    return r


def test_dq_empty(db):
    s = dq.run(db=db)
    assert s["total"] == 0
    assert s["score"] == 100.0


def test_dq_valid(db):
    _seed(db, [_base()])
    s = dq.run(db=db)
    assert s["total"] == 1 and s["valid"] == 1
    assert s["invalid"] == 0 and s["duplicate"] == 0


def test_dq_invalid_odds(db):
    _seed(db, [_base(odds=0), _base(smid="m2", mmid="mm2", odds=-1.5)])
    s = dq.run(db=db)
    assert s["invalid"] == 2


def test_dq_missing_fields(db):
    _seed(db, [_base(event_time=None)])
    s = dq.run(db=db)
    assert s["missing"] >= 1


def test_dq_duplicate(db):
    """规则 20/34: 重复数据被 DB UNIQUE 明确拒绝, 不无限产生重复记录。"""
    _seed(db, [_base(received_at=1000)])
    with pytest.raises(sqlite3.IntegrityError):
        _seed(db, [_base(received_at=1000)])  # 同 key 重复 -> 拒绝
    db.rollback()
    s = dq.run(db=db)
    assert s["total"] == 1  # 只保留 1 条


def test_dq_unmapped(db):
    _seed(db, [_base(canonical_match_id=None)])
    s = dq.run(db=db)
    assert s["unmapped"] == 1


def test_dq_stale(db):
    _seed(db, [_base(received_at=int(time.time() * 1000) - 99999999)])
    s = dq.run(db=db)
    assert s["stale"] == 1


def test_dq_out_of_order_gap(db):
    # 10:00, 10:01, 10:02, 10:10 -> 断档(规则 21 连续性)
    t0 = 1000000000000
    _seed(db, [
        _base(received_at=t0, option="a", mmid="m1"),
        _base(received_at=t0 + 60000, option="a", mmid="m2"),
        _base(received_at=t0 + 120000, option="a", mmid="m3"),
        _base(received_at=t0 + 1500000, option="a", mmid="m4"),
    ])
    s = dq.run(db=db)
    assert s["out_of_order"] == 1  # 10:02 -> 10:25 断档超 600s 阈值


def test_dq_conflict(db):
    """规则 21/33: Mapping 层 CONFLICT 被 DQ 识别。"""
    now = int(time.time() * 1000)
    db.execute("""insert into match_mappings(
        source,source_match_id,canonical_match_id,home,away,event_time,
        confidence,status,created_at,updated_at)
        values(?,?,?,?,?,?,?,?,?,?)""",
        ("bb", "m1", "cmA", "A", "B", now, 0.5, "CONFLICT", now, now))
    db.commit()
    s = dq.run(db=db)
    assert s["conflict"] >= 1


def test_dq_score_does_not_mask_errors(db):
    _seed(db, [_base(odds=-1)])  # 严重错误
    s = dq.run(db=db)
    assert s["score"] < 100
    assert s["invalid"] == 1  # 显式状态仍在
