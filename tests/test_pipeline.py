"""Integration + Pipeline Test(规则 40): 完整链路与分层职责。

用构造数据(非网络)走真实代码路径:
Normalized -> Match Mapping -> Market Mapping -> Unified
-> Event -> Feature -> Signal -> Strategy -> Decision

断言: 每层有产物、分层不越权、血缘可追踪、下游唯一入口(unified)。
"""
import json
import pytest

from events.engine_v3 import run as event_run
from events.group_v3 import run as group_run
from features.engine_v2 import run as feature_run
from signals.engine_v1 import run as signal_run
from strategies.engine_v1 import run as strategy_run
from decisions.engine_v1 import run as decision_run

from tests.helpers import seed_round


def test_pipeline_full(db):
    seed_round(db, 1000, "-0.5", 1.90)
    seed_round(db, 2000, "-0.75", 1.85)  # 让球加深 + 水位变化

    # EVENT: 只描述事实
    # bb m1: 让球 line -0.5->-0.75 (LINE_CHANGE), 大小 odds 1.90->1.85 (WATER_CHANGE)
    # sx e2: 无变化
    ev, details = event_run()
    assert ev >= 2, f"预期至少 2 个事件, 实际 {ev}"
    types = {r[0] for r in db.execute("select event_type from events_v3").fetchall()}
    assert "LINE_CHANGE" in types
    assert "WATER_CHANGE" in types

    # 事件行必须带血缘(规则 9/14)
    row = db.execute(
        "select unified_snapshot_id,pipeline_version,engine_version from events_v3 limit 1").fetchone()
    assert row["unified_snapshot_id"] is not None
    assert row["pipeline_version"] == "0.1.0"
    assert row["engine_version"] == "v3"

    gr = group_run()
    # GROUP 是组合聚合(同组内需 LINE+WATER 或双向 WATER);
    # 单场单盘口场景可能为 0, 链路完整性不受影响
    assert isinstance(gr, int) and gr >= 0

    # FEATURE: 结构化统计
    ft = feature_run()
    assert ft >= 1
    frow = db.execute(
        "select event_refs,pipeline_version,engine_version from features_v2 limit 1").fetchone()
    assert frow["event_refs"] and frow["pipeline_version"] == "0.1.0"
    assert frow["engine_version"] == "v2"

    # SIGNAL: Feature 满足条件才触发(数据不足时为 0, 属正确行为)
    sg = signal_run()
    assert isinstance(sg, int) and sg >= 0
    srow = db.execute(
        "select feature_id,pipeline_version from signals_v1 limit 1").fetchone()
    if srow:
        assert srow["feature_id"] is not None
        assert srow["pipeline_version"] == "0.1.0"

    # STRATEGY: 组合 Signal
    st = strategy_run()
    assert isinstance(st, int) and st >= 0
    strow = db.execute(
        "select signal_id,pipeline_version from strategies_v1 limit 1").fetchone()
    if strow:
        assert strow["signal_id"] is not None
        assert strow["pipeline_version"] == "0.1.0"

    # DECISION: 结构化候选, direction/selection 允许 UNKNOWN(规则 13)
    dc = decision_run()
    assert isinstance(dc, int) and dc >= 0
    drow = db.execute(
        "select strategy_id,status,pipeline_version,engine_version from decisions_v1 limit 1").fetchone()
    if drow:
        assert drow["strategy_id"] is not None
        assert drow["status"] in ("CANDIDATE",)
        assert drow["pipeline_version"] == "0.1.0"
        assert drow["engine_version"] == "v1"


def test_signal_strategy_decision_triggered(db):
    """Signal 条件满足时(规则 11): 多轮主客水位反向变化 => 触发链。"""
    for i in range(5):
        seed_round(db, 1000 + i * 1000, "-0.5", 2.0,
                   ah_odds=1.90 if i % 2 == 0 else 1.85,
                   ah_away_odds=1.85 if i % 2 == 0 else 1.90)

    ev, _ = event_run()
    assert ev >= 4
    gr = group_run()  # WATER_SHIFT 组
    assert gr >= 1
    feature_run()

    sg = signal_run()
    assert sg >= 1, "水位交替变化应触发 WATER_SHIFT_STRONG"

    st = strategy_run()
    assert st >= 1

    dc = decision_run()
    assert dc >= 1
    row = db.execute(
        "select status from decisions_v1 limit 1").fetchone()
    assert row["status"] == "CANDIDATE"


def test_unified_is_only_entry(db):
    """规则 8: 下游 Event 只消费 unified_snapshots(唯一标准入口)。"""
    seed_round(db, 1000, "-0.5", 1.90)
    seed_round(db, 2000, "-0.75", 1.85)

    event_run()
    ev = db.execute("select count(*) from events_v3").fetchone()[0]
    assert ev > 0

    # 事件中每一行都能 join 到 unified_snapshots
    orphans = db.execute("""
        select count(*) from events_v3 e
        left join unified_snapshots u on e.unified_snapshot_id = u.id
        where u.id is null
    """).fetchone()[0]
    assert orphans == 0


def test_single_round_no_events(db):
    """只有一个时间点: 无事件(需 >=2 时间点, 规则 21)。"""
    seed_round(db, 1000, "-0.5", 1.90)
    ev, details = event_run()
    assert ev == 0


def test_out_of_order_snapshots(db):
    """规则 21/22: 时间乱序插入也按 received_at 排序比较, 不产生错误事件。"""
    seed_round(db, 3000, "-0.75", 1.85)   # 先插入较晚时间
    seed_round(db, 1000, "-0.5", 1.90)    # 后插入较早时间
    seed_round(db, 2000, "-0.5", 1.95)    # 中间时间

    ev, details = event_run()
    # 1000->2000: odds 1.90->1.95 WATER_CHANGE
    # 2000->3000: line -0.5->-0.75 LINE_CHANGE + odds 1.95->1.85 WATER_CHANGE
    assert ev >= 3


def test_feature_based_on_events(db):
    """规则 10/49: Feature 基于 Event 引用(event_refs 指向 events_v3.id)。"""
    seed_round(db, 1000, "-0.5", 1.90)
    seed_round(db, 2000, "-0.75", 1.85)
    event_run()
    feature_run()
    frow = db.execute("select event_refs from features_v2 limit 1").fetchone()
    refs = json.loads(frow["event_refs"])
    assert refs and all(
        db.execute("select 1 from events_v3 where id=?", (x,)).fetchone()
        for x in refs)
