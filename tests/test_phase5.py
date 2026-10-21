"""Phase 5 测试: 赛事映射审计与人工确认(规格 §8)。

覆盖:
  1. 迁移 v6: 审计/审批表 + match_mappings 新列 + superseded 标记
  2. PENDING/CONFLICT -> 人工队列(候选+分数)
  3. approve: 选定候选生效 + 审计 + 旧下游标记失效
  4. reject / defer: 决策记录 + 审计
  5. revoke: 映射失效 + 下游 superseded + 审计(R3 完整闭环)
  6. auto_map 自动变更也留审计(R3 修复)
"""
import json

from database import db as database
from core import env
from mapping import audit as ma
from mapping.service import auto_map
from mapping.status import PENDING, CONFLICT, MAPPED
from tests.helpers import nrec


# ---------- 1. 迁移 v6 ----------

def test_migrate_v6(db):
    tables = {r[0] for r in db.execute(
        "select name from sqlite_master where type='table'")}
    assert "mapping_review_queue" in tables
    assert "mapping_audit" in tables
    mm_cols = [r[1] for r in db.execute(
        "PRAGMA table_info(match_mappings)")]
    for col in ("evidence", "rule_version", "approval",
                "valid_from", "valid_to", "operator", "note"):
        assert col in mm_cols, col
    us_cols = [r[1] for r in db.execute(
        "PRAGMA table_info(unified_snapshots)")]
    assert "superseded" in us_cols
    assert db.execute("PRAGMA user_version").fetchone()[0] == 7


def test_config_schema_version_is_6():
    assert env.schema_version() == 7


# ---------- 2. 候选进入人工队列 ----------

def test_pending_enters_review_queue(db):
    """跨源近候选: 分数落入 PENDING -> 人工队列。"""
    a = nrec("bb", "p1", "mm1", "1000", "-0.5", "主队-0.5", 1.9, 5000,
             home="Manchester United FC", away="Chelsea")
    b = nrec("sx", "e9", "mx1", "3", "-0.5", "Man United -0.5", 2.05, 5000,
             home="Man United", away="Chelsea London")
    r = auto_map(a, b, conn=db)
    assert r["status"] in (PENDING, CONFLICT), r
    rows = ma.list_queue(db, decision="pending")
    assert rows
    q = rows[0]
    assert q["source"] == "bb" and q["source_match_id"] == "p1"
    cands = json.loads(q["candidates_json"] or "[]")
    assert isinstance(cands, list)
    assert all("canonical_match_id" in c and "confidence" in c
               for c in cands)


def test_conflict_same_names_diff_time_queued(db):
    a = nrec("bb", "c1", "mm1", "1000", "-0.5", "主队-0.5", 1.9, 5000,
             home="Manchester United", away="Chelsea")
    b = nrec("sx", "e8", "mx1", "3", "-0.5", "Man United -0.5", 2.05, 5000,
             home="Manchester United", away="Chelsea",
             event_time=1000 + 30 * 60 * 60 * 1000)
    r = auto_map(a, b, conn=db)
    assert r["status"] == CONFLICT
    assert ma.list_queue(db)  # 同名不同时间 -> 人工, 禁止强行合并


# ---------- 3. approve ----------

def test_approve_flow(db):
    # 造一条已确认映射作为候选
    seed = nrec("bb", "s1", "mm1", "1000", "-0.5", "主队-0.5", 1.9, 5000,
                home="Manchester United", away="Chelsea")
    auto_map(seed, seed, conn=db)
    db.execute("""UPDATE match_mappings
                  SET canonical_match_id='cm_MANUTD_VS_CHE'
                  WHERE source='bb' AND source_match_id='s1'""")
    # 直接造一条 pending 评审: 候选 = 上面那条映射
    a = nrec("bb", "p2", "mm1", "1000", "-0.5", "主队-0.5", 1.9, 5000,
             home="Man Utd", away="Chelsea")
    cands = [{"canonical_match_id": "cm_MANUTD_VS_CHE",
              "home": "Manchester United", "away": "Chelsea",
              "event_time": 5000, "confidence": 0.9,
              "home_score": 0.9, "away_score": 1.0,
              "time_score": 1.0, "status": "MAPPED", "reps": 1}]
    ma.queue_pending(db, a, {"status": "PENDING"}, cands)
    db.commit()
    q = ma.list_queue(db)[0]
    out = ma.approve(db, q["id"], operator="tester", note="手工确认",
                     candidate_index=0)
    db.commit()
    assert out["canonical_match_id"] == "cm_MANUTD_VS_CHE"
    row = db.execute(
        "select approval, operator, note, status from match_mappings "
        "where source='bb' and source_match_id='p2'").fetchone()
    assert row[0] == "manual" and row[1] == "tester"
    assert row[2] == "手工确认" and row[3] == "MAPPED"
    # 审计记录
    audit = ma.audit_log(db, source="bb", source_match_id="p2")
    assert any(r["action"] == "manual_approve" for r in audit)
    # 队列已决
    assert ma.list_queue(db) == []


# ---------- 4. reject / defer ----------

def test_reject_and_defer(db):
    a = nrec("bb", "p3", "mm1", "1000", "-0.5", "主队-0.5", 1.9, 5000,
             home="Manchester United FC", away="Chelsea")
    b = nrec("sx", "e9", "mx1", "3", "-0.5", "Man United -0.5", 2.05, 5000,
             home="Man United", away="Chelsea London")
    auto_map(a, b, conn=db)
    q = ma.list_queue(db)[0]
    ma.reject(db, q["id"], operator="tester", note="非同一场比赛")
    db.commit()
    assert ma.list_queue(db) == []
    assert ma.audit_log(db, source="bb", source_match_id="p3")
    # defer
    auto_map(a, b, conn=db)  # 已决 rejected 不被打回
    assert ma.list_queue(db) == []
    q2 = ma.list_queue(db, decision="rejected")[0]
    ma.defer(db, q2["id"], operator="tester", note="等更多证据")
    db.commit()
    assert ma.list_queue(db, decision="deferred")


# ---------- 5. revoke 与下游失效 ----------

def test_revoke_invalidates_downstream(db):
    # 写入一条已映射 + 一条 unified
    seed = nrec("bb", "r1", "mm1", "1000", "-0.5", "主队-0.5", 1.9, 1000,
                home="Manchester United", away="Chelsea")
    auto_map(seed, seed, conn=db)
    db.execute("""UPDATE match_mappings
                  SET canonical_match_id='cm_REVOKE_ME'
                  WHERE source='bb' AND source_match_id='r1'""")
    db.execute("""INSERT INTO unified_snapshots(
        canonical_match_id, source, source_match_id, source_market_id,
        market_type, option, odds, received_at, created_at)
        VALUES('cm_REVOKE_ME','bb','r1','mm1','1000','主队-0.5',
               1.9, 1000, 1000)""")
    db.commit()
    out = ma.revoke(db, "bb", "r1", operator="tester", note="ID 复用")
    db.commit()
    assert out["canonical_match_id"] == "cm_REVOKE_ME"
    row = db.execute(
        "select status, valid_to from match_mappings "
        "where source='bb' and source_match_id='r1'").fetchone()
    assert row[0] == "REVOKED" and row[1] is not None
    # 旧 unified 结果保留但标记 superseded
    snap = db.execute(
        "select superseded from unified_snapshots "
        "where canonical_match_id='cm_REVOKE_ME'").fetchone()
    assert snap[0] == 1
    assert ma.audit_log(db, source="bb", source_match_id="r1")


# ---------- 6. 自动变更审计(R3) ----------

def test_auto_save_audited(db):
    a = nrec("bb", "a1", "mm1", "1000", "-0.5", "主队-0.5", 1.9, 1000,
             home="Manchester United", away="Chelsea")
    auto_map(a, a, conn=db)
    db.commit()
    n1 = len(ma.audit_log(db, source="bb", source_match_id="a1"))
    assert n1 == 1
    # 同输入再次 auto_map: canonical 不变 -> 不新增审计
    auto_map(a, a, conn=db)
    db.commit()
    assert len(ma.audit_log(db, source="bb", source_match_id="a1")) == 1
    # 变更事件时间 -> canonical 变化 -> 新增 auto_approve 审计
    a2 = nrec("bb", "a1", "mm1", "1000", "-0.5", "主队-0.5", 1.9, 5000,
              home="Manchester United", away="Chelsea",
              event_time=1000 + 5 * 60 * 60 * 1000)
    auto_map(a2, a2, conn=db)
    db.commit()
    log = ma.audit_log(db, source="bb", source_match_id="a1")
    assert len(log) == 2
    assert log[0]["action"] == "auto_approve"
    assert log[0]["old_canonical_match_id"] != log[0]["new_canonical_match_id"]
