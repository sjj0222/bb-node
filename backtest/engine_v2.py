"""Backtest Engine V2(V0.2 P0-7, 规则 36~38)。

建立在 Replay 之上(V1 保留为 legacy)。
- 分组: Match / Market / Source / Strategy / Time Window / 版本(规则 36)
- 输出: sample_count / trigger_count / success_count / failure_count /
  success_rate / result_distribution(规则 37)
- 无可靠结果字段不虚构 ROI(规则 25/37)
- 参数比较: 同一 Replay 数据 + 不同 Strategy 参数(规则 38)
"""
import os
import time
import json
import sqlite3
from core import env
from database import db as database
from replay.engine_v2 import replay_db_path

ENGINE_VERSION = "v2"


def run(db=None, group_by="match", strategy_plugins=None,
        match_ids=None, sources=None, market_types=None,
        window=None):
    """Backtest V0.2。group_by: match|market|source|strategy|time|version。"""
    dbfile = db or replay_db_path()
    if not os.path.exists(dbfile):
        print("BACKTEST V2: replay db not found:", dbfile)
        return None

    c = sqlite3.connect(dbfile)
    c.row_factory = sqlite3.Row
    try:
        def cnt(sql, args=()):
            return c.execute(sql, args).fetchone()[0]

        # 样本: 特征窗口数(每个 feature 行 = 一次可评估窗口)
        sample_count = cnt("select count(*) from features_v2")
        trigger_count = cnt("select count(*) from strategies_v1 "
                            "where status='TRIGGERED'")
        decision_count = cnt("select count(*) from decisions_v1")

        result_distribution = [
            dict(r) for r in c.execute(
                "select status,count(*) n from decisions_v1 group by status")
        ]

        groups = []
        if group_by == "match":
            q = """select canonical_match_id k,
                      count(distinct id) samples,
                      sum(case when status='TRIGGERED' then 1 else 0 end) trig
                   from strategies_v1 group by canonical_match_id"""
        elif group_by == "market":
            q = """select market_type k,
                      count(distinct id) samples,
                      sum(case when status='TRIGGERED' then 1 else 0 end) trig
                   from strategies_v1 group by market_type"""
        elif group_by == "source":
            q = """select source k,
                      count(distinct id) samples,
                      sum(case when status='TRIGGERED' then 1 else 0 end) trig
                   from strategies_v1 group by source"""
        elif group_by == "strategy":
            q = """select strategy_name k,
                      count(distinct id) samples,
                      sum(case when status='TRIGGERED' then 1 else 0 end) trig
                   from strategies_v1 group by strategy_name"""
        elif group_by == "time":
            q = """select (new_time/3600000) k,
                      count(distinct id) samples,
                      sum(case when status='TRIGGERED' then 1 else 0 end) trig
                   from strategies_v1 group by k"""
        elif group_by == "version":
            q = """select engine_version k,
                      count(distinct id) samples,
                      sum(case when status='TRIGGERED' then 1 else 0 end) trig
                   from strategies_v1 group by engine_version"""
        else:
            raise ValueError("unknown group_by: %s" % group_by)

        for r in c.execute(q):
            samples = r["samples"] or 0
            trig = r["trig"] or 0
            groups.append({
                "group": r["k"],
                "sample_count": samples,
                "trigger_count": trig,
                "success_count": 0,      # 无结果字段, 不虚构(规则 25/37)
                "failure_count": 0,
                "success_rate": None,
            })

        summary = {
            "engine": ENGINE_VERSION,
            "group_by": group_by,
            "sample_count": sample_count,
            "trigger_count": trigger_count,
            "decision_count": decision_count,
            "success_count": 0,
            "failure_count": 0,
            "success_rate": None,
            "result_distribution": result_distribution,
            "groups": groups,
        }

        now = int(time.time() * 1000)
        pc = database.connect()
        pc.execute("""insert into backtest_runs_v2(
            replay_id,strategy_plugin,group_by,sample_count,trigger_count,
            success_count,failure_count,success_rate,result_distribution,
            params,created_at)
            values(?,?,?,?,?,?,?,?,?,?,?)""",
            (0, json.dumps(strategy_plugins or []), group_by,
             sample_count, trigger_count, 0, 0, None,
             json.dumps(result_distribution, ensure_ascii=False),
             json.dumps({"match_ids": match_ids, "sources": sources,
                         "market_types": market_types, "window": window},
                        ensure_ascii=False),
             now))
        pc.commit()
        pc.close()

        print("=== BACKTEST V2 ===")
        print("group_by:", group_by, "samples:", sample_count,
              "triggered:", trigger_count, "decisions:", decision_count)
        print("groups:", json.dumps(groups, ensure_ascii=False)[:400])
        return summary
    finally:
        c.close()


def compare_strategies(db=None, strategy_plugins=("ah_multi_level_water",)):
    """参数/策略比较(规则 38): 同一 Replay 数据上分别统计。"""
    dbfile = db or replay_db_path()
    if not os.path.exists(dbfile):
        return None
    out = {}
    for sp in strategy_plugins:
        s = run(db=dbfile, group_by="strategy", strategy_plugins=[sp])
        out[sp] = s
    return out


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--group-by", default="match")
    args = ap.parse_args()
    run(group_by=args.group_by)


if __name__ == "__main__":
    main()
