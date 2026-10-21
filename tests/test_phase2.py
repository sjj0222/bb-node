"""Phase 2 测试: RAW 观测历史 / 采集幂等 / 未映射落库 / 分页 partial。

覆盖(规格 4.3 raw_records/raw_observations/ingest_runs, 风险 R2/R4):
  1. 迁移 v4: 新表存在、collection_runs 增强列、幂等
  2. _ledger_raw: 同一 payload 重复出现 -> seen_count 累积、观测保序
  3. _ledger_unmapped / _process_records: 未映射记录落库不丢弃
  4. bb 分页: 中途失败 -> meta.partial=True, error_code=PAGE_FAILED
  5. _finish_run: partial/error_code/pages/retries 落库
"""
import json
import sqlite3

from sources.base import NormalizedRecord
from sources import bb as bb_mod
from sources import sx as sx_mod
from core import collector
from core import env
from database import db as database
from mapping.service import auto_map
from tests.helpers import nrec


# ---------- 1. 迁移 v4 ----------

def test_migrate_v4_tables_and_columns(db):
    con = db
    tables = {r[0] for r in con.execute(
        "select name from sqlite_master where type='table'")}
    for t in ("raw_records", "raw_observations", "unmapped_records",
              "quality_errors"):
        assert t in tables, t
    cols = [r[1] for r in con.execute("PRAGMA table_info(collection_runs)")]
    for col in ("run_type", "pages", "retries", "partial",
                "records_duplicate", "error_code"):
        assert col in cols, col
    uv = con.execute("PRAGMA user_version").fetchone()[0]
    assert uv == 5


def test_migrate_v4_idempotent(db):
    database.init()          # 第二次迁移
    database.init()          # 第三次(幂等, 不报错不重复)
    con = database.connect()
    integrity = con.execute("PRAGMA integrity_check").fetchone()[0]
    assert integrity == "ok"
    n = con.execute("select count(*) from raw_records").fetchone()[0]
    assert n == 0
    con.close()


# ---------- 2. RAW 落账 ----------

def test_ledger_raw_accumulates_and_preserves_observations(db, tmp_path):
    con = db
    content_hash = "a" * 64
    # 同一 payload 两次观测
    collector._ledger_raw(con, "bb", content_hash, 1000, 1)
    collector._ledger_raw(con, "bb", content_hash, 2000, 2)
    con.commit()
    rows = con.execute(
        "select source,content_hash,seen_count,first_seen_ms,last_seen_ms "
        "from raw_records").fetchall()
    assert len(rows) == 1
    source, ch, seen, first, last = rows[0]
    assert ch == content_hash
    assert seen == 2
    assert first <= last  # 首见时间只写一次, 末见时间单调
    # 第三次观测: first 不变, seen 继续累积
    collector._ledger_raw(con, "bb", content_hash, 3000, 3)
    con.commit()
    row = con.execute(
        "select seen_count,first_seen_ms,last_seen_ms from raw_records"
    ).fetchone()
    assert row[0] == 3
    assert row[1] == first
    assert row[2] >= last
    obs = con.execute(
        "select count(*) from raw_observations").fetchone()[0]
    assert obs == 3       # 三次观测保序保留


def test_ledger_unmapped_dedup_by_reason(db):
    con = db
    now = 3000
    collector._ledger_unmapped(con, "bb", "m1", "MATCH_UNMAPPED", {"a": 1})
    collector._ledger_unmapped(con, "bb", "m1", "MATCH_UNMAPPED", {"a": 1})
    collector._ledger_unmapped(con, "bb", "m1", "MARKET_UNMAPPED", {"a": 1})
    con.commit()
    rows = con.execute(
        "select reason,seen_count from unmapped_records "
        "order by reason").fetchall()
    by_reason = dict(rows)
    assert by_reason["MATCH_UNMAPPED"] == 2
    assert by_reason["MARKET_UNMAPPED"] == 1


def test_process_records_ledgers_unmapped(db):
    """未映射/无效记录落库不丢弃(R4)。

    场景1: 空队伍 -> MATCH_INVALID; 场景2: 未知盘口类型 -> MARKET_UNMAPPED。
    """
    con = db
    counts = {"mapped": 0, "unmapped": 0, "invalid": 0,
              "pending": 0, "unified": 0}
    # 场景1: 空队伍(无效)
    bad_match = nrec("bb", "m_bad", "mm9", "1000", "-0.5", "主队-0.5",
                     1.9, 5000, home="", away="")
    collector._process_records([bad_match], counts, con,
                               source="bb", run_id=7)
    # 场景2: 未知盘口类型(未映射)
    bad_market = nrec("bb", "m_mkt", "mm9", "9999", "1.5", "某种选项",
                      1.9, 5000, home="Manchester United", away="Chelsea")
    collector._process_records([bad_market], counts, con,
                               source="bb", run_id=8)
    con.commit()
    rows = con.execute(
        "select source_match_id,reason from unmapped_records "
        "order by source_match_id").fetchall()
    by_smid = dict(rows)
    assert by_smid["m_bad"] == "MATCH_INVALID"
    assert by_smid["m_mkt"] == "MARKET_UNMAPPED"
    # 未映射内容保留原始字段
    row = con.execute(
        "select normalized_json from unmapped_records where source_match_id=?",
        ("m_mkt",)).fetchone()
    parsed = json.loads(row[0])
    assert parsed["market_type"] == "9999"


# ---------- 3. 分页 partial(R2) ----------

class _FakeBB(bb_mod.BBAdapter):
    """第二页失败一次后再成功的模拟分页。"""

    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self.calls = 0
        self._fail_page = 2

    def _get_page_with_retries(self, page, typ):
        self.calls += 1
        if page == self._fail_page:
            return None, 3      # 3 次重试均失败
        return {"success": True, "data": {
            "records": [{"id": page * 10, "lg": {"id": 11062}}],
            "total": 3, "size": 1}}, 0


def test_bb_fetch_with_meta_partial(db):
    a = _FakeBB()
    matches, meta = a.fetch_with_meta(3, received_at=1000)
    assert meta["partial"] is True          # R2: 不再静默成功
    assert meta["error_code"] == "PAGE_FAILED"
    assert meta["pages"] == 2
    assert meta["retries"] == 3
    # 已成功页的数据仍保留(不丢失已抓取)
    assert any(m.get("id") == 10 for m in matches.values())


def test_bb_fetch_compat_returns_dict(db):
    a = _FakeBB()
    matches = a.fetch(3, received_at=1000)
    assert isinstance(matches, dict)


def test_sx_fetch_sets_meta(db):
    a = sx_mod.SXBetAdapter()
    # 未调用 fetch 时 getattr 返回 None 的兜底
    assert collector._collect_meta(a)["partial"] is False


def test_collect_meta_helper():
    class A:
        last_collect_meta = {"pages": 4, "retries": 2,
                             "partial": True, "error_code": "PAGE_FAILED"}
    m = collector._collect_meta(A(), "3")
    assert m["pages"] == 4 and m["retries"] == 2
    assert m["partial"] is True and m["error_code"] == "PAGE_FAILED"
    assert m["run_type"] == "3"


def test_finish_run_writes_meta(db):
    run_id = collector._new_run("bb", run_type="3")
    collector._finish_run(run_id, 2, 5, True,
                          meta={"pages": 3, "retries": 1,
                                "partial": True, "error_code": "PAGE_FAILED",
                                "run_type": "3"})
    row = db.execute(
        "select success,partial,pages,retries,error_code,run_type "
        "from collection_runs where id=?", (run_id,)).fetchone()
    assert row[0] == 1
    assert row[1] == 1
    assert row[2] == 3 and row[3] == 1
    assert row[4] == "PAGE_FAILED"
    assert row[5] == "3"


def test_finish_run_failure_keeps_meta(db):
    run_id = collector._new_run("bb")
    collector._finish_run(run_id, 0, 0, False, "boom",
                          meta={"partial": True, "error_code": "PAGE_FAILED"})
    row = db.execute(
        "select success,partial,error_code from collection_runs where id=?",
        (run_id,)).fetchone()
    assert row[0] == 0 and row[1] == 1 and row[2] == "PAGE_FAILED"
    assert db.execute("select error from collection_runs where id=?",
                      (run_id,)).fetchone()[0] == "boom"


# ---------- 4. 配置 schema_version ----------

def test_config_schema_version_is_5():
    assert env.schema_version() == 5
