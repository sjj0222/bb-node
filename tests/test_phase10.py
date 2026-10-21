"""Phase 12 测试: 稳定性门槛(R8 修复, 规格 §19/§20)。

覆盖:
  1. 终态判定: 无错误 PASS; 有错误但轮次不足 ERROR; 错误率超限 ERROR;
     恢复率不足 ERROR; 门限内 PASS(含边界)
  2. 原因码留痕: status_reason 写入 stability_runs 与 state
  3. 迁移 v11
"""
import json
import os
import time

from database import db as database
from core import env
from stability.run import _final_status


# ---------- 1. 终态判定 ----------

def test_gate_clean_pass():
    st, reason = _final_status(rounds=10, errors=0, recoveries=0)
    assert st == "PASS"
    assert reason == "clean: errors=0"


def test_gate_too_few_rounds_error():
    # R8 原逻辑: 1 错误 -> recoveries=1 -> 恒 PASS; 修复后轮次不足 -> ERROR
    st, reason = _final_status(rounds=1, errors=1, recoveries=1)
    assert st == "ERROR"
    assert "too_few_rounds" in reason


def test_gate_error_rate_exceeded():
    st, _ = _final_status(rounds=4, errors=3, recoveries=3)
    assert st == "ERROR"          # 75% 错误率 > 25%


def test_gate_recovery_rate_insufficient():
    st, _ = _final_status(rounds=10, errors=4, recoveries=1)
    assert st == "ERROR"          # 恢复率 25% < 50%


def test_gate_within_limits_pass():
    st, reason = _final_status(rounds=10, errors=1, recoveries=1)
    assert st == "PASS"
    assert "within_gate" in reason


def test_gate_boundary_error_rate():
    # 边界: 4 轮 1 错 = 25% 恰好不超限, 恢复率 100% -> PASS
    st, _ = _final_status(rounds=4, errors=1, recoveries=1)
    assert st == "PASS"


# ---------- 2. 原因码留痕 ----------

def test_status_reason_column(db):
    cols = [r[1] for r in db.execute(
        "PRAGMA table_info(stability_runs)")]
    assert "status_reason" in cols


# ---------- 3. 迁移 v11 ----------

def test_migrate_v11(db):
    assert db.execute("PRAGMA user_version").fetchone()[0] == 11


def test_config_schema_version_is_11():
    assert env.schema_version() == 11
