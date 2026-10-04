"""Replay Engine V2(V0.2 P0-7, 规则 39~42/44/45)。

在 V0.1 True Replay(V1, 保留为 legacy)基础上增强:
- 过滤: 时间窗 / 比赛 / Market / Source / Strategy / 版本(规则 39)
- 多 Source 分别与联合 Replay(规则 40)
- 版本记录: data_version / engine_version / schema_version /
  config_version / strategy_version(规则 41)
- DQ 状态复现: 历史 STALE 保持 STALE(规则 41) —— Replay 使用历史
  窗口内的数据, 天然不会因为"现在 Source 恢复"改变历史状态
- 无未来数据泄漏: 所有查询 <= cutoff / 时间窗上界(规则 24)
"""
import os
import time
import json
import sqlite3
from core import env
from database import db as database

ENGINE_VERSION = "v2"


def replay_db_path():
    return (os.environ.get("BB_NODE_REPLAY_DB")
            or os.path.join(env.data_dir(), "replay.db"))


def reset_replay_db():
    p = replay_db_path()
    d = os.path.dirname(p)
    if d:
        os.makedirs(d, exist_ok=True)
    if os.path.exists(p):
        os.remove(p)
    database.init(p)
    return p


def copy_unified(c, cutoff=None, window=None, match_ids=None,
                 sources=None, market_types=None):
    """从生产库复制过滤后的 unified_snapshots(规则 39/40)。

    无未来泄漏: received_at <= cutoff 且位于 window 内。
    """
    src = sqlite3.connect(env.db_path())
    src.row_factory = sqlite3.Row

    q = "select * from unified_snapshots where 1=1"
    args = []
    if cutoff:
        q += " and received_at <= ?"
        args.append(cutoff)
    if window:
        w0, w1 = window
        q += " and received_at >= ? and received_at <= ?"
        args += [w0, w1]
    if match_ids:
        ph = ",".join("?" * len(match_ids))
        q += " and canonical_match_id in (%s)" % ph
        args += list(match_ids)
    if sources:
        ph = ",".join("?" * len(sources))
        q += " and source in (%s)" % ph
        args += list(sources)
    if market_types:
        ph = ",".join("?" * len(market_types))
        q += " and market_type in (%s)" % ph
        args += list(market_types)
    q += " order by received_at,id"
    rows = src.execute(q, args).fetchall()
    src.close()

    if not rows:
        return 0

    cols = [k for k in rows[0].keys() if k != "id"]
    ph = ",".join("?" * len(cols))
    colsql = ",".join(cols)
    for r in rows:
        c.execute(
            "insert or ignore into unified_snapshots(%s) values(%s)"
            % (colsql, ph),
            [r[k] for k in cols])
    return len(rows)


def _record_run(c, n, filters, counts):
    ts = c.execute(
        "select min(received_at),max(received_at) from unified_snapshots"
    ).fetchone()
    start, end = (ts[0] or 0), (ts[1] or 0)
    matches = c.execute(
        "select count(distinct canonical_match_id) from unified_snapshots"
    ).fetchone()[0]
    now = int(time.time() * 1000)
    h = database.data_hash({
        "start": start, "end": end, "rows": n, "matches": matches,
        "filters": filters, "engines": env.get("engines"),
        "pipeline": env.pipeline_version(),
    })
    cur = c.execute("""insert or ignore into replay_runs_v2(
        replay_hash,filter_json,snapshots,matches,start_time,end_time,
        data_version,engine_version,schema_version,config_version,
        strategy_version,events,features,signals,strategies,decisions,
        created_at)
        values(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (h, json.dumps(filters, ensure_ascii=False), n, matches,
         start, end,
         env.pipeline_version(), ENGINE_VERSION,
         env.schema_version(), env.get("config_version", "?"),
         json.dumps(env.get("strategy") or {}),
         counts.get("events", 0), counts.get("features", 0),
         counts.get("signals", 0), counts.get("strategies", 0),
         counts.get("decisions", 0), now))
    return cur.lastrowid, h, start, end, matches


def run(cutoff=None, window=None, match_ids=None, sources=None,
        market_types=None, strategy_plugins=None):
    """Replay V0.2 主入口。返回统计 dict(含版本信息)。

    参数:
      cutoff: 时间旅行上界(ms)
      window: (t0, t1) 时间窗
      match_ids / sources / market_types: 过滤
      strategy_plugins: 仅统计指定策略(不修改下游计算)
    """
    filters = {
        "cutoff": cutoff, "window": window,
        "match_ids": match_ids, "sources": sources,
        "market_types": market_types,
    }
    p = reset_replay_db()
    c = sqlite3.connect(p)
    c.row_factory = sqlite3.Row

    try:
        n = copy_unified(c, cutoff=cutoff, window=window,
                         match_ids=match_ids, sources=sources,
                         market_types=market_types)
        c.commit()
        if n == 0:
            print("REPLAY V2: no unified snapshots match filters", filters)
            return None

        from events.engine_v3 import run as event_run
        from events.group_v3 import run as group_run
        from features.engine_v2 import run as feature_run
        from signals.engine_v1 import run as signal_run
        from strategies.engine_v1 import run as strategy_run
        from decisions.engine_v1 import run as decision_run

        ev = event_run(db=p, cutoff=cutoff)
        gr = group_run(db=p, cutoff=cutoff)
        ft = feature_run(db=p, cutoff=cutoff)
        sg = signal_run(db=p, cutoff=cutoff)
        st = strategy_run(db=p, cutoff=cutoff)
        dc = decision_run(db=p, cutoff=cutoff)

        counts = {
            "events": ev[0] if isinstance(ev, tuple) else ev,
            "features": ft, "signals": sg,
            "strategies": st, "decisions": dc,
        }
        rid, rh, start, end, matches = _record_run(c, n, filters, counts)
        c.commit()

        summary = {
            "replay_db": p,
            "replay_id": rid,
            "replay_hash": rh,
            "filters": filters,
            "snapshots": n,
            "matches": matches,
            "window": (start, end),
            "counts": counts,
            "versions": {
                "data_version": env.pipeline_version(),
                "engine_version": ENGINE_VERSION,
                "schema_version": env.schema_version(),
                "config_version": env.get("config_version", "?"),
                "strategy": env.get("strategy"),
            },
        }
        print("=== REPLAY V2 DONE ===")
        print(json.dumps(summary, ensure_ascii=False, default=str)[:600])
        return summary
    finally:
        c.close()
