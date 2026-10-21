"""Phase 7 测试: Unified 与查询性能(规格 §9)。

覆盖:
  1. 迁移 v8: league_id/content_hash/time_quality 列 + 最新值视图
  2. 时间三态分离: event_time/observed_at/ingested_at 显式暴露,
     来源时间缺失标记 time_quality 不伪造
  3. content_hash: 稳定、变更可检测
  4. query_unified: 多条件过滤(联赛/来源/盘口线/赔率/新鲜度/映射状态)
  5. latest_unified_quotes 视图: 最新值查询
  6. market_series: 时间序列(追加不覆盖)
  7. cross_source_compare: 每来源独立报价保留(不平均)
  8. plan_report: EXPLAIN 基线
"""
import time

from database import db as database
from core import env
from mapping.unified_service import unify
from unified import query as uq
from tests.helpers import nrec


def _put(db, *, smid="m1", source="bb", mmid="k1", mtype="1000",
         line_raw="-0.5", option="主队-0.5", odds=1.90, received_at=None,
         event_time=1700000000000, league=11062):
    received_at = received_at or int(time.time() * 1000)
    rec = nrec("bb", smid, mmid, mtype, line_raw, option, odds,
               received_at, event_time=event_time, league_id=league,
               home="Manchester United", away="Chelsea")
    unify(rec, canonical_match_id="cm_q7_" + smid, conn=db)


# ---------- 1. 迁移 v8 ----------

def test_migrate_v8(db):
    us_cols = [r[1] for r in db.execute(
        "PRAGMA table_info(unified_snapshots)")]
    for col in ("league_id", "content_hash", "time_quality"):
        assert col in us_cols, col
    v = db.execute(
        "select name from sqlite_master where type='view'").fetchall()
    assert any(r[0] == "latest_unified_quotes" for r in v)
    assert db.execute("PRAGMA user_version").fetchone()[0] == 9


def test_config_schema_version_is_8():
    assert env.schema_version() == 9


# ---------- 2/3. 时间三态 + content_hash ----------

def test_time_three_state_and_quality(db):
    _put(db, received_at=1234567, event_time=1700000000000)
    _put(db, smid="m2", received_at=7654321, event_time=None)
    db.commit()
    row = db.execute(
        "select event_time, received_at, created_at, time_quality "
        "from unified_snapshots where source_match_id='m2'").fetchone()
    assert row[0] is None                 # 来源时间缺失不伪造
    assert row[2] >= row[1]               # ingested_at >= observed_at
    assert row[3] == "approx"             # 时间质量显式标记
    row1 = db.execute(
        "select time_quality from unified_snapshots "
        "where source_match_id='m1'").fetchone()
    assert row1[0] == "ok"


def test_content_hash_stable_and_detect_change(db):
    _put(db, smid="h1", odds=1.90, received_at=5000)
    _put(db, smid="h1", odds=1.90, received_at=5000)
    db.commit()
    rows = db.execute(
        "select content_hash from unified_snapshots "
        "where source_match_id='h1' order by id").fetchall()
    # 同内容(同 received_at 幂等唯一) -> 实际只有 1 行
    assert len(rows) == 1
    _put(db, smid="h2", odds=1.90, received_at=6000)
    _put(db, smid="h3", odds=2.10, received_at=6000)
    db.commit()
    h2 = db.execute("select content_hash from unified_snapshots "
                    "where source_match_id='h2'").fetchone()[0]
    h3 = db.execute("select content_hash from unified_snapshots "
                    "where source_match_id='h3'").fetchone()[0]
    assert h2 and h3 and h2 != h3          # 赔率变化 -> 哈希变化


# ---------- 4. 查询过滤 ----------

def test_query_filters(db):
    _put(db, smid="f1", odds=1.90, league=11062)
    _put(db, smid="f2", odds=3.50, league=11062)
    _put(db, smid="f3", odds=1.50, league=11140)
    db.commit()
    assert len(uq.query_unified(db, league=11062)) == 2
    assert len(uq.query_unified(db, min_odds=2.0)) == 1
    assert len(uq.query_unified(db, max_odds=2.0)) == 2
    assert len(uq.query_unified(db, line=-0.5)) == 3
    rows = uq.query_unified(db, source="bb", market_type="asian_handicap",
                            side="HOME")
    assert rows and rows[0]["side"] == "HOME"


def test_query_mapping_status(db):
    _put(db, smid="f0", odds=1.90, league=11062)
    db.execute("""INSERT INTO unified_snapshots(
        canonical_match_id,source,source_match_id,source_market_id,
        market_type,option,odds,received_at,created_at)
        VALUES(NULL,'bb','unmapped1','k9','asian_handicap','x',1.9,
               1000,1000)""")
    db.commit()
    mapped = uq.query_unified(db, mapping_status="mapped")
    assert mapped and all(r["canonical_match_id"] for r in mapped)
    unmapped = uq.query_unified(db, mapping_status="unmapped")
    assert any(r["source_match_id"] == "unmapped1" for r in unmapped)


# ---------- 5/6/7. 视图 / 序列 / 跨源 ----------

def test_latest_quotes_view(db):
    now = int(time.time() * 1000)
    _put(db, smid="v1", odds=1.90, received_at=now - 2000)
    _put(db, smid="v1", odds=2.10, received_at=now)
    db.commit()
    latest = uq.latest_quotes(db, match_id="cm_q7_v1")
    assert latest and latest[0]["odds"] == 2.10      # 最新值
    assert latest[0]["observed_at"] == now
    assert "ingested_at" in latest[0]
    assert "event_time" in latest[0]


def test_market_series_appends(db):
    now = int(time.time() * 1000)
    _put(db, smid="s1", odds=1.90, received_at=now - 4000)
    _put(db, smid="s1", odds=2.05, received_at=now - 2000)
    _put(db, smid="s1", odds=2.30, received_at=now)
    db.commit()
    series = uq.market_series(db, "cm_q7_s1", "asian_handicap")
    assert len(series) == 3              # 历史保留, 追加不覆盖
    odds = [r["odds"] for r in series]
    assert odds == sorted(odds)          # 按时间升序


def test_cross_source_compare_no_average(db):
    now = int(time.time() * 1000)
    _put(db, smid="c1", odds=1.90, received_at=now - 1000)
    # sx 报价
    rec = nrec("sx", "sx1", "mx1", "3", "-0.5", "MU -0.5", 2.05,
               now, event_time=1700000000000, home="Manchester United",
               away="Chelsea")
    unify(rec, canonical_match_id="cm_q7_c1", conn=db)
    db.commit()
    cmp = uq.cross_source_compare(db, "cm_q7_c1", "asian_handicap")
    assert len(cmp) == 2                 # 两个来源独立保留
    by_source = {r["source"]: r["odds"] for r in cmp}
    assert by_source["bb"] == 1.90       # 不平均覆盖
    assert by_source["sx"] == 2.05

# ---------- 8. EXPLAIN 基线 ----------

def test_plan_report(db):
    report = uq.plan_report(db)
    assert len(report) == 3
    for r in report:
        assert r["plan_lines"]
        assert r["plan"][0]["detail"]
