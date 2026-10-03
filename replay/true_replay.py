"""True Replay(规则 23/24) —— 从历史数据重跑完整下游 Pipeline。

- 输入: Historical Unified(unified_snapshots, 可带 cutoff 时间旅行)
- 重放: EVENT -> FEATURE -> SIGNAL -> STRATEGY -> DECISION(与生产同引擎)
- 隔离: 在独立 replay.db 中执行, 不污染生产库
- 确定性: 引擎全部确定性; 相同输入 + 相同 cutoff => 业务结果一致
- 无未来泄漏: cutoff 过滤, 只使用 <= cutoff 的快照(规则 24)
"""
import os
import time
import sqlite3

from core import env
from database import db as database


def replay_db_path():
    return (os.environ.get("BB_NODE_REPLAY_DB")
            or os.path.join(env.data_dir(), "replay.db"))


def reset_replay_db():
    p = replay_db_path()
    d = os.path.dirname(p)
    if d:
        os.makedirs(d, exist_ok=True)
    if os.path.exists(p):
        os.remove(p)  # 重建, 保证确定性起点
    database.init(p)
    return p


def copy_unified(c, cutoff=None):
    """从生产库复制 unified_snapshots(<=cutoff) 到 replay 库。返回行数。"""
    src = sqlite3.connect(env.db_path())
    src.row_factory = sqlite3.Row
    if cutoff:
        rows = src.execute("""select * from unified_snapshots
            where received_at <= ? order by received_at,id""",
                           (cutoff,)).fetchall()
    else:
        rows = src.execute(
            "select * from unified_snapshots order by received_at,id").fetchall()
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


def _record_run(c, n, cutoff):
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
        "cutoff": cutoff, "engines": env.get("engines"),
        "pipeline": env.pipeline_version(),
    })
    cur = c.execute("""insert or ignore into replay_runs_v1(
        start_time,end_time,rows,matches,replay_hash,created_at)
        values(?,?,?,?,?,?)""",
        (start, end, n, matches, h, now))
    return cur.lastrowid, h, start, end, matches


def run(cutoff=None):
    """True Replay 主入口。返回统计 dict。"""
    p = reset_replay_db()
    c = sqlite3.connect(p)
    c.row_factory = sqlite3.Row

    try:
        n = copy_unified(c, cutoff)
        c.commit()
        if n == 0:
            print("REPLAY: no unified snapshots <= cutoff", cutoff)
            return None

        rid, rh, start, end, matches = _record_run(c, n, cutoff)
        c.commit()
        c.close()

        print("=== TRUE REPLAY ===")
        print("db:", p)
        print("snapshots:", n, "matches:", matches,
              "window:", start, "->", end, "cutoff:", cutoff)
        print("replay_hash:", rh[:24])

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

        summary = {
            "replay_db": p,
            "replay_id": rid,
            "replay_hash": rh,
            "snapshots": n,
            "matches": matches,
            "start": start,
            "end": end,
            "cutoff": cutoff,
            "events": ev,
            "groups": gr,
            "features": ft,
            "signals": sg,
            "strategies": st,
            "decisions": dc,
        }
        print("=== REPLAY DONE ===", summary)
        return summary
    except Exception:
        try:
            c.close()
        except Exception:
            pass
        raise
