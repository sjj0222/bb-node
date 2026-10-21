"""Phase 6 测试: 盘口字段规范与主盘口选择器(规格 §5, R1 修复)。

覆盖:
  1. parse_line_quarters 编码: R1 符号反转修复 + 边界编码
  2. odds_raw 保留 / line_quarters 落 unified
  3. 主盘口选择器: 来源优先级 / 停盘 / 无候选 no_selection / 冲突
  4. 选择结果落 main_selections 并可查
  5. 盘口质量校验(§5.4): MARKET_LINE_REQUIRED
"""
import json

from database import db as database
from core import env, collector
from mapping import market as mkt
from mapping.unified_service import unify
from market import selector as sel
from quality import validator as v
from tests.helpers import nrec


# ---------- 1. line_quarters 编码(R1) ----------

def test_quarters_negative_split_sign_preserved():
    """R1 修复: '-0/0.5' 不得反转成 +0.25。"""
    lq, mid = mkt.parse_line_quarters("-0/0.5")
    assert lq == "-2:0"
    assert mid == -1                 # -0.25


def test_quarters_positive_split():
    lq, mid = mkt.parse_line_quarters("+0/0.5")
    assert lq == "0:2"
    assert mid == 1                  # +0.25


def test_quarters_plain():
    assert mkt.parse_line_quarters("-0.5") == ("-2:-2", -2)
    assert mkt.parse_line_quarters("2.5") == ("10:10", 10)
    assert mkt.parse_line_quarters("-0.25") == ("-1:-1", -1)
    assert mkt.parse_line_quarters(None) == (None, None)
    assert mkt.parse_line_quarters("abc") == (None, None)


def test_quarters_market_normalize():
    rec = nrec("bb", "m1", "mm1", "1000", "-0/0.5", "主队-0/0.5", 1.9,
               5000, odds_raw="1.9")
    m = mkt.normalize(rec)
    assert m.line_quarters == "-2:0"   # 新编码只对新数据生效
    assert m.odds_raw == "1.9"


# ---------- 2. odds_raw / line_quarters 落 unified ----------

def test_unified_keeps_odds_raw_and_quarters(db):
    rec = nrec("bb", "m1", "mm1", "1000", "-0.5", "主队-0.5", 1.90, 5000,
               odds_raw="1.90")
    unify(rec, canonical_match_id="cm_q", conn=db)
    db.commit()
    row = db.execute(
        "select odds_raw, line_quarters from unified_snapshots "
        "where canonical_match_id='cm_q'").fetchone()
    assert row[0] == "1.90"
    assert row[1] == "-2:-2"


# ---------- 3. 主盘口选择器 ----------

def _seed_snapshots(db):
    import time
    now = int(time.time() * 1000)
    base = dict(canonical_match_id="cm_sel", source="bb",
                source_market_id="k1", market_type="asian_handicap",
                period="full_time", line=-0.5, line_quarters="-2:-2",
                option="主队-0.5", odds=1.90, received_at=now - 5000,
                created_at=now - 5000)
    db.execute("""INSERT INTO unified_snapshots(
        canonical_match_id,source,source_match_id,source_market_id,
        market_type,period,line,line_quarters,option,odds,
        received_at,created_at)
        VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
               (base["canonical_match_id"], base["source"], "bb1",
                base["source_market_id"], base["market_type"],
                base["period"], base["line"], base["line_quarters"],
                base["option"], base["odds"], base["received_at"],
                base["created_at"]))
    db.execute("""INSERT INTO unified_snapshots(
        canonical_match_id,source,source_match_id,source_market_id,
        market_type,period,line,line_quarters,option,odds,
        received_at,created_at)
        VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
               (base["canonical_match_id"], "sx", "sx1",
                base["source_market_id"], base["market_type"],
                base["period"], base["line"], base["line_quarters"],
                "MU -0.5", 2.05, now - 3000, now - 3000))


def test_selector_priority_and_persist(db):
    _seed_snapshots(db)
    db.commit()
    out = sel.select_main(db, "cm_sel", "asian_handicap", "full_time",
                          policy={"require_fresh_ms": 60000})
    assert out["quality_status"] == "selected"
    assert out["selected_source_id"] == "bb"      # 来源优先级 bb > sx
    assert sel.REASON_OK in out["selection_reason_codes"]
    assert out["data_as_of_time"] is not None
    # 落库可查
    latest = sel.latest_selection(db, "cm_sel", "asian_handicap")
    assert latest and latest["selected_source_id"] == "bb"
    assert latest["selection_reason_codes"] == out["selection_reason_codes"]


def test_selector_suspended_skip(db):
    _seed_snapshots(db)
    # 唯一候选停盘(odds=1.0)
    db.execute("""UPDATE unified_snapshots SET odds=1.0
                  WHERE source_match_id='bb1'""")
    db.execute("""UPDATE unified_snapshots SET odds=1.0
                  WHERE source_match_id='sx1'""")
    db.commit()
    out = sel.select_main(db, "cm_sel", "asian_handicap", "full_time")
    assert out["quality_status"] == "no_selection"
    assert sel.REASON_NO_CANDIDATE in out["selection_reason_codes"]
    assert out["selected_quote_ids"] == []


def test_selector_no_candidate(db):
    out = sel.select_main(db, "cm_none", "asian_handicap", "full_time")
    assert out["quality_status"] == "no_selection"   # 不猜
    assert sel.REASON_NO_CANDIDATE in out["selection_reason_codes"]


def test_selector_conflict_no_selection_policy(db):
    _seed_snapshots(db)
    db.execute("""UPDATE unified_snapshots SET line=-1.0, line_quarters='-4:-4'
                  WHERE source_match_id='sx1'""")
    db.commit()
    out = sel.select_main(db, "cm_sel", "asian_handicap", "full_time",
                          policy={"on_conflict": "no_selection"})
    assert out["quality_status"] == "no_selection"
    assert sel.REASON_CONFLICT in out["selection_reason_codes"]
    # 默认策略: 来源优先级优先(bb), 冲突记录原因码, 不放弃
    out2 = sel.select_main(db, "cm_sel", "asian_handicap", "full_time")
    assert out2["quality_status"] == "selected"
    assert out2["selected_source_id"] == "bb"
    assert sel.REASON_CONFLICT in out2["selection_reason_codes"]


def test_selector_stale_skip(db):
    _seed_snapshots(db)
    out = sel.select_main(db, "cm_sel", "asian_handicap", "full_time",
                          policy={"require_fresh_ms": 100})
    # 两条都超龄 -> 无候选
    assert out["quality_status"] == "no_selection"
    assert sel.REASON_STALE_SKIP in out["selection_reason_codes"]


# ---------- 4. 盘口质量校验(§5.4) ----------

def test_validator_market_line_required():
    rec = nrec("bb", "m1", "mm1", "1000", None, "主队-0.5", 1.9, 5000,
               line=None)
    errs = v.validate(rec)
    assert any(code == v.MARKET_LINE_REQUIRED for _, code, _ in errs)


def test_validator_market_line_ok_with_raw():
    rec = nrec("bb", "m1", "mm1", "1000", "-0/0.5", "主队-0/0.5", 1.9,
               5000, line=None)
    errs = v.validate(rec)
    assert not any(code == v.MARKET_LINE_REQUIRED for _, code, _ in errs)


# ---------- 5. 迁移 v7 ----------

def test_migrate_v7(db):
    tables = {r[0] for r in db.execute(
        "select name from sqlite_master where type='table'")}
    assert "main_selections" in tables
    us_cols = [r[1] for r in db.execute(
        "PRAGMA table_info(unified_snapshots)")]
    assert "odds_raw" in us_cols and "line_quarters" in us_cols
    assert db.execute("PRAGMA user_version").fetchone()[0] == 11


def test_config_schema_version_is_7():
    assert env.schema_version() == 11
