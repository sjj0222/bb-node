"""审计反馈 P3 回归(P3-12 状态枚举 / P3-13 run_id / P3-14 依赖 / P3-15 计数 /
P3-16 jitter / P3-17 import 副作用 / P3-18 双重归一化 / P3-19 init_* 残表)。"""
import os
import subprocess
import sys
import time
from unittest import mock

from core import checks
from core import log
from core import status as st
from database import db as database
from sources.contract import backoff_sleep
from tests.helpers import nrec


# ---- P3-12: checks 状态串与 log 实际写入一致 ----

def test_pipeline_check_matches_log_status(db):
    """成功采集(log 写 OK) -> doctor 必须报 OK, 不得再报 FAIL。"""
    for status, want in (("OK", "OK"), ("RUNNING", "RUNNING"),
                         ("ERROR", "FAIL")):
        db.execute(
            "INSERT INTO pipeline_runs(run_id,stage,source,start_time,status)"
            " VALUES(?,?,?,?,?)", ("r-%d" % time.time_ns(), "COLLECT", "bb",
                                   int(time.time() * 1000), status))
        db.commit()
        item = checks.pipeline_check()[0]
        assert item["status"] == want, (
            "log 写入 %r 时 checks 应报 %r, 实际 %r" % (
                status, want, item["status"]))


# ---- P3-13: run_id 唯一(uuid), 不再毫秒时间戳 ----

def test_start_run_id_unique_uuid(db):
    a = log.start("COLLECT", "bb")
    b = log.start("COLLECT", "sx")
    assert a != b
    assert a.startswith("run-") and not a.replace("run-", "").isdigit(), (
        "run_id 应为 uuid 前缀格式, 实际 %r" % a)
    # finish 只更新自己的 run_id
    log.finish(a, "OK", 1, 1)
    rows = db.execute(
        "SELECT run_id,status FROM pipeline_runs "
        "WHERE run_id IN (?,?) ORDER BY run_id", (a, b)).fetchall()
    sts = {r[0]: r[1] for r in rows}
    assert sts[a] == "OK"
    assert sts[b] == "RUNNING"


# ---- P3-14: requirements.txt 与真实依赖一致 ----

def test_requirements_declares_requests():
    repo = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    text = open(os.path.join(repo, "requirements.txt"), encoding="utf-8").read()
    assert "requests" in text
    assert "纯 Python 标准库" not in text, "不得再声称无第三方运行时依赖"
    assert "当前未使用" not in text


# ---- P3-15: row_count 不重复计数 ----

def test_row_count_counts_each_record_once(monkeypatch, db):
    """1 条 MAPPED 记录 -> collection_runs.row_count == 1(修复前 2)。"""
    from core import collector

    class FakeAdapter:
        source = "bb"
        last_collect_meta = {"pages": 1, "retries": 0,
                             "partial": False, "error_code": None}

        def collect(self, typ, received_at):
            return {"m1": {"raw_ref": "r1", "received_at": received_at,
                           "match": {"id": 1}}}

        def normalize(self, match, received_at, raw_ref=None):
            return [nrec("bb", "m1", "mm1", "1000", "-0.5", "主队-0.5",
                         1.90, received_at)]

    monkeypatch.setattr(collector, "get_adapter", lambda name: FakeAdapter())
    result = collector.collect_source("bb")
    assert result["rows"] == 1, "一条记录应只计一次, 实际 %d" % result["rows"]
    row = db.execute("SELECT row_count FROM collection_runs "
                     "ORDER BY id DESC LIMIT 1").fetchone()
    assert row[0] == 1


# ---- P3-16: jitter 不突破退避上限 ----

def test_backoff_capped_after_jitter():
    with mock.patch("sources.contract.time.sleep") as sl:
        backoff_sleep({"backoff_base": 2.0, "backoff_max": 20.0,
                       "jitter": [1.5, 1.5]}, attempt=10)
    assert sl.call_count == 1
    wait = sl.call_args[0][0]
    assert wait <= 20.0, "抖动后仍不得突破 cap, 实际睡 %.1fs" % wait


# ---- P3-17: import 无副作用 + 路径不冻结 ----

def test_log_import_no_side_effects():
    """全新进程 import core.log: 不建库、不建日志文件(修复前会建)。"""
    repo = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    env_p = dict(os.environ)
    env_p["BB_NODE_HOME"] = "/tmp/bbnode_nosd_%d" % time.time_ns()
    env_p.pop("BB_NODE_DB", None)
    env_p.pop("BB_NODE_LOG", None)
    env_p.pop("BB_NODE_CONFIG", None)
    env_p.pop("BB_NODE_REPLAY_DB", None)
    r = subprocess.run(
        [sys.executable, "-c",
         "import sys; sys.path.insert(0, %r); import core.log; "
         "import core.status; import core.health; import database.db; "
         "print('ok')" % repo],
        env=env_p, capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stderr
    home = env_p["BB_NODE_HOME"]
    assert not os.path.exists(os.path.join(home, "data", "bb.db"))
    assert not os.path.exists(os.path.join(home, "data", "logs", "bb-node.log"))


def test_db_path_not_frozen_at_import(monkeypatch):
    """import 之后设置的 BB_NODE_DB 生效(不再顶层冻结)。"""
    target = "/tmp/bbnode_late_%d/late.db" % time.time_ns()
    monkeypatch.setenv("BB_NODE_DB", target)
    c = database.connect()
    try:
        c.execute("CREATE TABLE IF NOT EXISTS _late_ok(id INTEGER)")
        c.commit()
    finally:
        c.close()
    assert os.path.exists(target), "connect 应使用 import 后设置的路径"


# ---- P3-18: 同一条记录只归一化一次 ----

def test_unify_market_reuses_normalized(monkeypatch, db):
    """unify_market 不再调用 normalize(修复前 collector 先 map 再 unify
    会 normalize 两次)。"""
    from mapping import unified_service
    rec = nrec("bb", "m1", "mm1", "1000", "-0.5", "主队-0.5", 1.90, 1000)
    from mapping.market_service import map_and_save
    mkt = map_and_save(rec, canonical_match_id="cid1", conn=db)
    monkeypatch.setattr(
        unified_service, "normalize",
        mock.Mock(side_effect=AssertionError("不应再次 normalize")))
    unified_service.unify_market(rec, mkt, canonical_match_id="cid1",
                                 conn=db)
    db.commit()
    assert db.execute(
        "SELECT count(*) FROM unified_snapshots").fetchone()[0] == 1


# ---- P3-19: init_* 不得抢先建残表 ----

def test_init_unified_builds_full_schema(tmp_path):
    """单独调 init_unified() 后写入必须成功(修复前缺 odds_raw 列崩)。"""
    dbfile = str(tmp_path / "u.db")
    from mapping.unified_db import init_unified, save_unified
    init_unified(dbfile)
    c = database.connect(dbfile)
    try:
        cols = {r[1] for r in c.execute(
            "PRAGMA table_info(unified_snapshots)")}
        for need in ("odds_raw", "line_quarters", "content_hash",
                     "time_quality", "superseded"):
            assert need in cols, "init_unified 后仍缺列 %s" % need
        rec = type("U", (), {
            "source": "bb", "bookmaker": "BB", "source_match_id": "m1",
            "source_market_id": "mm1", "market_type": "1000", "period": "0",
            "line_raw": "-0.5", "line": -0.5, "line_quarters": None,
            "side": "HOME", "option": "主队-0.5", "odds": 1.90,
            "odds_raw": "1.90", "event_time": 1000, "server_time": 1000,
            "received_at": 1000, "raw_ref": "raw", "league_id": None,
            "pipeline_version": "t", "status": "MAPPED"})()
        save_unified(rec, "cid1", conn=c)   # 写入不抛 no such column
    finally:
        c.close()


def test_init_market_mapping_and_mapping_full_schema(tmp_path):
    dbfile = str(tmp_path / "m.db")
    from mapping.market_db import init_market_mapping
    from mapping.db import init_mapping
    init_market_mapping(dbfile)
    init_mapping(dbfile)
    c = database.connect(dbfile)
    try:
        cols = {r[1] for r in c.execute(
            "PRAGMA table_info(match_mappings)")}
        for need in ("evidence", "rule_version", "approval",
                     "valid_from", "valid_to", "operator", "note"):
            assert need in cols, "init_mapping 后仍缺列 %s" % need
    finally:
        c.close()
