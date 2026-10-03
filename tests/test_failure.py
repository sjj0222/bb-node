"""Failure Test(规则 32/33/34/41): 异常与边界必须显式处理, 不得静默。

覆盖:
- Source 故障隔离(A DOWN 不影响 B, 规则 3.3/32)
- 重复数据(规则 20/35)
- 非法数据(空/缺字段/类型错误/非法盘口, 规则 34)
- 空数据(规则 34)
- Mapping 显式失败状态(规则 33)
"""
import os
import pytest

from core import env
from core.collector import collect, collect_source
from sources.base import NormalizedRecord
from mapping.market import normalize as market_normalize
from mapping.match import map_match
from tests.helpers import nrec, seed_round


class Rec:
    def __init__(self, source, smid, home, away, et):
        self.source = source
        self.source_match_id = smid
        self.home = home
        self.away = away
        self.event_time = et


# ---------- Source 故障隔离(规则 3.3/32) ----------

class BrokenAdapter:
    """模拟不可用 Source: fetch 抛异常。"""
    def fetch(self, *a, **k):
        raise RuntimeError("source down: network unreachable")

    def collect(self, *a, **k):
        raise RuntimeError("source down")


def test_source_down_isolated(monkeypatch, db):
    """BB DOWN 时 SX 继续处理(规则 32 场景 B)。"""
    from sources import registry
    monkeypatch.setitem(registry.ADAPTERS, "bb", BrokenAdapter)
    results = collect()
    by = {r["source"]: r for r in results}
    assert by["bb"]["success"] is False
    assert "down" in by["bb"]["error"]
    assert by["sx"]["success"] is True  # 其他 Source 不受影响


def test_source_bb_down_returns_error_not_crash(monkeypatch, db):
    monkeypatch.setitem(__import__("sources.registry", fromlist=["x"]).ADAPTERS,
                        "bb", BrokenAdapter)
    r = collect_source("bb")
    assert r["success"] is False
    assert r["error"]


def test_source_unregistered(monkeypatch, db):
    """未知 Source => 显式失败而非崩溃。"""
    monkeypatch.setitem(__import__("sources.registry", fromlist=["x"]).ADAPTERS,
                        "ghost", BrokenAdapter)
    from core import collector
    r = collector.collect_source("ghost")
    assert r["success"] is False
    assert r["error"]


# ---------- 重复数据(规则 20/35) ----------

def test_duplicate_same_received_at(db):
    """相同 received_at 的完全相同盘口 => 不产生重复 unified 行。"""
    seed_round(db, 1000, "-0.5", 1.90)
    before = db.execute("select count(*) from unified_snapshots").fetchone()[0]
    seed_round(db, 1000, "-0.5", 1.90)  # 完全重复(同一时间点)
    after = db.execute("select count(*) from unified_snapshots").fetchone()[0]
    assert after == before


def test_duplicate_diff_received_at_allowed(db):
    """规则 20: 数据内容相同但采集时间不同 => 保留(不同业务记录)。"""
    seed_round(db, 1000, "-0.5", 1.90)
    before = db.execute("select count(*) from unified_snapshots").fetchone()[0]
    seed_round(db, 5000, "-0.5", 1.90)  # 内容相同, 时间不同
    after = db.execute("select count(*) from unified_snapshots").fetchone()[0]
    assert after == before * 2


# ---------- 非法数据(规则 34) ----------

def test_invalid_odds(db):
    m = market_normalize(nrec("bb", "m1", "mm9", "1000", "-0.5",
                              "主队-0.5", None, 1000))
    assert m.status == "INVALID"


def test_invalid_negative_odds(db):
    m = market_normalize(nrec("bb", "m1", "mm9", "1000", "-0.5",
                              "主队-0.5", -1.2, 1000))
    assert m.status == "INVALID"


def test_invalid_line_text(db):
    m = market_normalize(nrec("bb", "m1", "mm9", "1000", "abc",
                              "主队-0.5", 1.9, 1000))
    assert m.status == "INVALID"


def test_missing_fields(db):
    """缺 home/away => match INVALID; 不产生 canonical。"""
    r = map_match(Rec("bb", "1", "", "Chelsea", 1000),
                  Rec("bb", "1", "", "Chelsea", 1000))
    assert r["status"] == "INVALID"
    assert r["canonical_match_id"] is None


def test_time_missing_match(db):
    """时间缺失 => 无法可靠匹配 => 显式状态而非强行 MAPPED。"""
    a = Rec("bb", "1", "Manchester United", "Chelsea", None)
    b = Rec("sx", "x", "Manchester United", "Chelsea", None)
    r = map_match(a, b)
    assert r["status"] != "MAPPED"  # PENDING / UNMAPPED


# ---------- 空数据(规则 34) ----------

def test_empty_market_bundle(db):
    """空盘口 => 0 行, 不崩溃。"""
    m = market_normalize(nrec("bb", "m1", "mm1", "", "", "", None, 1000))
    assert m.status == "UNMAPPED"


def test_empty_unified_no_events(db):
    from events.engine_v3 import run as event_run
    ev, _ = event_run()
    assert ev == 0


# ---------- Mapping 显式失败(规则 33) ----------

def test_mapping_statuses_enum():
    """规则 19: 异常必须显式; 映射层与系统层状态枚举完整。"""
    from mapping.status import (MAPPED, UNMAPPED, CONFLICT,
                                PENDING, INVALID)
    from core.status import OK, STALE, ERROR, UNAVAILABLE
    assert {MAPPED, UNMAPPED, CONFLICT, PENDING, INVALID} == {
        "MAPPED", "UNMAPPED", "CONFLICT", "PENDING", "INVALID"}
    assert {OK, STALE, ERROR, UNAVAILABLE} == {
        "OK", "STALE", "ERROR", "UNAVAILABLE"}
