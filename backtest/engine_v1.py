"""Backtest Engine V1(规则 25) —— 建立在 Replay 之上。

统计:
  - 样本数(窗口/事件/特征)
  - 触发次数(Signal / Strategy / Decision)
  - 不同 Signal 类型 / Strategy 类型数量与分布
  - Decision 状态分布

当前系统无结果/ROI 字段, 不虚构结果(规则 25: 不允许为制造 ROI 虚构数据)。
"""
import os
import sqlite3
import time

from core import env
from database import db as database
from replay.true_replay import replay_db_path

ENGINE_VERSION = "v1"


def run(db=None, replay_cutoff=None):
    dbfile = db or replay_db_path()
    if not os.path.exists(dbfile):
        print("BACKTEST: replay db not found:", dbfile)
        return None

    c = sqlite3.connect(dbfile)
    c.row_factory = sqlite3.Row

    try:
        def count(sql, args=()):
            return c.execute(sql, args).fetchone()[0]

        events = count("select count(*) from events_v3")
        groups = count("select count(*) from event_groups_v3")
        features = count("select count(*) from features_v2")
        signals = count("select count(*) from signals_v1")
        strategies = count("select count(*) from strategies_v1")
        decisions = count("select count(*) from decisions_v1")

        signal_dist = [
            dict(r) for r in c.execute(
                "select signal_type,count(*) n from signals_v1 group by signal_type")
        ]
        strategy_dist = [
            dict(r) for r in c.execute(
                "select strategy_name,status,count(*) n from strategies_v1 group by strategy_name,status")
        ]
        decision_dist = [
            dict(r) for r in c.execute(
                "select status,count(*) n from decisions_v1 group by status")
        ]
        event_dist = [
            dict(r) for r in c.execute(
                "select event_type,count(*) n from events_v3 group by event_type")
        ]

        summary = {
            "events": events,
            "groups": groups,
            "features": features,
            "signals": signals,
            "strategies": strategies,
            "decisions": decisions,
            "signal_dist": signal_dist,
            "strategy_dist": strategy_dist,
            "decision_dist": decision_dist,
            "event_dist": event_dist,
        }

        now = int(time.time() * 1000)
        # 在生产库记录一次 backtest run
        pc = database.connect()
        pc.execute("""insert into backtest_runs_v1(
            replay_id,samples,triggered,signal_types,strategy_types,created_at)
            values(?,?,?,?,?,?)""",
            (0, features, signals + strategies + decisions,
             len(signal_dist), len(strategy_dist), now))
        pc.commit()
        pc.close()

        print("=== BACKTEST ===")
        print("samples(features):", features)
        print("events:", events, "groups:", groups)
        print("signals:", signals, "strategies:", strategies,
              "decisions:", decisions)
        print("signal_dist:", signal_dist)
        print("strategy_dist:", strategy_dist)
        print("decision_dist:", decision_dist)
        return summary
    finally:
        c.close()


def main():
    run()


if __name__ == "__main__":
    main()
