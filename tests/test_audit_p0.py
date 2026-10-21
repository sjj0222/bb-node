"""审计反馈 P0 回归(P0-1 schema 兜底降级 / P0-2 health_of 返回类型)。

覆盖审计盲区: BB_NODE_HOME 指向外部目录且无 config 的场景、
health_of 空 start_time、doctor 配置损坏检测。
"""
import os
import subprocess
import sys
import time

import pytest

from core import env
from core import checks
from core import status as st
from database import db as database


def _no_config(monkeypatch):
    """把基础配置指向不存在的路径(模拟 BB_NODE_HOME 外部目录无 config)。"""
    monkeypatch.setenv("BB_NODE_CONFIG", "/nonexistent/bb-node/config.json")


# ---- P0-1: schema_version 兜底必须等于代码 DDL 真实版本 ----

def test_schema_fallback_equals_db_constant(monkeypatch):
    _no_config(monkeypatch)
    # 配置缺失时: 兜底 = 代码 DDL 真实版本, 而不是 2
    assert env.schema_version() == database.SCHEMA_VERSION
    assert env.schema_version() == 11


def test_load_config_strict_fails_without_config(monkeypatch):
    _no_config(monkeypatch)
    with pytest.raises(env.ConfigError):
        env.load_config(strict=True)


def test_home_without_config_builds_v11_not_v2(tmp_path, monkeypatch):
    """复现审计 P0-1: BB_NODE_HOME 外部目录无 config 时建库。

    修复前: schema_version 兜底 2 → 迁移只到 v2 → unified_snapshots
    缺 odds_raw 列, save_unified 崩。修复后: 建出 v11 全列库。
    """
    _no_config(monkeypatch)
    dbfile = str(tmp_path / "home_without_config.db")
    database.init(dbfile)
    c = database.connect(dbfile)
    try:
        assert c.execute("PRAGMA user_version").fetchone()[0] == 11
        cols = {r[1] for r in c.execute(
            "PRAGMA table_info(unified_snapshots)")}
        for need in ("odds_raw", "line_quarters", "league_id",
                     "content_hash", "time_quality", "superseded"):
            assert need in cols, "缺列 %s: 建出的库是残缺的" % need
    finally:
        c.close()


def test_doctor_reports_config_fail_without_config(monkeypatch):
    """doctor 对配置缺失必须报 FAIL(自检不再全绿)。"""
    _no_config(monkeypatch)
    results = checks.run_checks()
    cfg = [r for r in results if r["name"] == "config_parse"][0]
    assert cfg["status"] == "FAIL"


def test_cli_exits_2_on_broken_config(tmp_path):
    """配置损坏时, 采集类命令 hard fail(exit 2), 不再静默降级。"""
    repo = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    broken = tmp_path / "broken.json"
    broken.write_text('{"database": {"schema_version": 11,,}', encoding="utf-8")
    env_p = dict(os.environ)
    env_p["BB_NODE_CONFIG"] = str(broken)
    r = subprocess.run(
        [sys.executable, os.path.join(repo, "cli.py"), "collect", "bb"],
        env=env_p, capture_output=True, text=True, timeout=60)
    assert r.returncode == 2, "配置损坏应 exit 2, 实际 %s: %s" % (
        r.returncode, r.stderr)


# ---- P0-2: health_of 返回类型恒定 tuple ----

def test_health_of_no_run_returns_tuple():
    state, age = st.health_of(None)
    assert state == st.NO_RUN
    assert age is None


def test_health_of_with_time_returns_tuple():
    state, age = st.health_of(int(time.time() * 1000) - 1000)
    assert isinstance(state, str)
    assert isinstance(age, (int, float))
    assert state in (st.OK, st.STALE, st.RUNNING)


def test_get_status_with_null_start_time(db):
    """pipeline_runs.start_time 为 NULL 时 status 面板不得抛异常。"""
    db.execute(
        "INSERT INTO pipeline_runs(stage, source, status, start_time) "
        "VALUES ('COLLECT', 'bb', 'OK', NULL)")
    db.commit()
    rows = st.get_status()
    row = [r for r in rows if r["stage"] == "COLLECT"][0]
    assert row["health"] == st.NO_RUN
    assert row["age_s"] is None
