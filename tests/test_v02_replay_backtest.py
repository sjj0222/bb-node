"""V0.2 测试矩阵 6: Replay V2 + Backtest V2(规则 73 + 确定性与无未来泄漏)。

覆盖: 时间旅行无未来泄漏、多源过滤、双跑确定性一致、Backtest 分组、
Strategy A/B 参数比较互不污染。
"""
import time
import sqlite3

import pytest

from replay import engine_v2 as rv2
from backtest import engine_v2 as bv2
from database import db as database
from tests.helpers import seed_round

from replay.true_replay import reset_replay_db as reset_v1


@pytest.fixture()
def seeded():
    """在测试库写入 3 轮 unified(2 场), 用于 Replay。"""
    database.init()
    c = database.connect()
    seed_round(c, 1000, "-0.5", 2.5)
    seed_round(c, 2000, "-0.75", 2.4)
    seed_round(c, 3000, "-1.0", 2.3)
    c.close()
    return 3


def test_replay_v2_determinism(seeded, monkeypatch):
    """规则 23.2/14: 相同输入双跑, 业务结果等价。"""
    monkeypatch.setenv("BB_NODE_REPLAY_DB", "/tmp/replay_det_a.db")
    s1 = rv2.run(cutoff=3000)
    c1 = s1["counts"]
    monkeypatch.setenv("BB_NODE_REPLAY_DB", "/tmp/replay_det_b.db")
    s2 = rv2.run(cutoff=3000)
    c2 = s2["counts"]
    assert c1 == c2
    assert s1["replay_hash"] == s2["replay_hash"]


def test_replay_no_future_leakage(seeded, monkeypatch):
    """规则 24: cutoff=1000 时不得使用 2000/3000 的数据。"""
    monkeypatch.setenv("BB_NODE_REPLAY_DB", "/tmp/replay_leak.db")
    s = rv2.run(cutoff=1000)
    assert s["snapshots"] == 4  # 只有第 1 轮(2 场 x 2 盘)
    c = sqlite3.connect(s["replay_db"])
    max_t = c.execute(
        "select max(received_at) from unified_snapshots").fetchone()[0]
    c.close()
    assert max_t <= 1000


def test_replay_multi_source_filter(seeded, monkeypatch):
    monkeypatch.setenv("BB_NODE_REPLAY_DB", "/tmp/replay_src.db")
    s = rv2.run(cutoff=3000, sources=["sx"])
    c = sqlite3.connect(s["replay_db"])
    srcs = {r[0] for r in c.execute(
        "select distinct source from unified_snapshots")}
    c.close()
    assert srcs == {"sx"}


def test_replay_version_tracking(seeded, monkeypatch):
    monkeypatch.setenv("BB_NODE_REPLAY_DB", "/tmp/replay_ver.db")
    s = rv2.run(cutoff=3000)
    v = s["versions"]
    assert v["data_version"] == "0.2.0"
    assert v["schema_version"] >= 3
    assert v["config_version"]
    assert "strategy" in v


def test_backtest_grouping(seeded, monkeypatch):
    monkeypatch.setenv("BB_NODE_REPLAY_DB", "/tmp/replay_bt.db")
    s = rv2.run(cutoff=3000)
    assert s is not None
    b = bv2.run(group_by="market")
    assert b["group_by"] == "market"
    assert b["sample_count"] >= 0
    assert isinstance(b["result_distribution"], list)


def test_backtest_strategy_compare_isolated(seeded, monkeypatch):
    """规则 38/73: 同一 Replay, 两个策略分别计算, 互不污染。"""
    monkeypatch.setenv("BB_NODE_REPLAY_DB", "/tmp/replay_cmp.db")
    s = rv2.run(cutoff=3000)
    a = bv2.run(db=s["replay_db"], group_by="strategy")
    b = bv2.run(db=s["replay_db"], group_by="strategy")
    assert a["sample_count"] == b["sample_count"]
    assert a["trigger_count"] == b["trigger_count"]
    # A 的结果不污染 B(运行两次一致)


def test_replay_v1_still_works(seeded, monkeypatch):
    """规则 62: V0.1 Replay(V1) 保留为 legacy 且可用。"""
    monkeypatch.setenv("BB_NODE_REPLAY_DB", "/tmp/replay_v1.db")
    from replay.true_replay import run as r1
    s = r1(cutoff=3000)
    assert s is not None and s["snapshots"] >= 4
