"""Replay Test(规则 23/24/40): True Replay 确定性 + 时间旅行无未来泄漏。"""
import os
import pytest

from database import db as database
from replay.true_replay import run as replay_run
from tests.helpers import seed_round


def business_summary(s):
    """从 replay summary 提取业务等价结果(忽略 DB 内部 ID)。"""
    assert s is not None
    return {
        "events": s["events"][0],
        "groups": s["groups"],
        "features": s["features"],
        "signals": s["signals"],
        "strategies": s["strategies"],
        "decisions": s["decisions"],
    }


def seed_prod_rounds():
    conn = database.connect()
    seed_round(conn, 1000, "-0.5", 1.90)
    seed_round(conn, 2000, "-0.75", 1.85)
    seed_round(conn, 3000, "-1.0", 1.80)
    conn.close()


def test_replay_deterministic(db):
    """规则 14/23: 相同输入两次 Replay => 业务结果等价。"""
    seed_prod_rounds()
    s1 = replay_run()
    s2 = replay_run()  # 第二次: 独立重建 replay 库
    assert business_summary(s1) == business_summary(s2)


def test_replay_no_future_leak(db):
    """规则 24: cutoff=1500 => 只看到第一轮(1000), 不能使用 2000/3000 数据。"""
    seed_prod_rounds()
    s = replay_run(cutoff=1500)
    assert s is not None
    # 只有一轮快照 => 无事件(需 >=2 时间点), 且快照数 = 第一轮 4 条
    assert s["snapshots"] == 4
    assert s["events"][0] == 0
    # 时间窗上界 <= cutoff
    assert s["end"] <= 1500


def test_replay_cutoff_partial(db):
    """cutoff=2500 => 使用 1000+2000 两轮, 不用 3000。"""
    seed_prod_rounds()
    s = replay_run(cutoff=2500)
    assert s["snapshots"] == 8
    assert s["end"] <= 2500
    assert s["events"][0] > 0


def test_replay_isolated_db(db):
    """规则 23.1: Replay 在独立 replay.db 执行, 不污染生产库。"""
    seed_prod_rounds()
    prod = os.environ["BB_NODE_DB"]

    def prod_files():
        base = os.path.basename(prod)
        return {f for f in os.listdir(os.path.dirname(prod))
                if f.startswith(base)}

    before = prod_files()
    replay_run()
    after = prod_files()
    assert before == after


def test_replay_empty(db):
    """空历史: Replay 返回 None 不崩溃。"""
    s = replay_run()
    assert s is None
