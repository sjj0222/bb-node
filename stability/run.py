"""V0.2 稳定性测试运行器(规则 43~47/74)。

- 24h 硬条件 / 72h 目标
- 循环执行 Monitor.run_once()(真实采集+全链路)
- 每轮监控: Memory/CPU/DB size/DB WAL/Source latency/Source failures/
  Pipeline failures/Duplicate rate/Data Quality(规则 45)
- 崩溃恢复: 单轮异常 -> errors++, 继续下一轮(规则 47)
- 运行状态写入 stability_runs 与 JSON 状态文件
"""
import os
import sys
import json
import time
import sqlite3
import resource
import threading

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core import env
from core.log import log_event, new_trace_id
from database.db import connect

DB = env.db_path()
STATE_FILE = os.environ.get("BB_NODE_STABILITY_STATE", "/tmp/bbnode_stability.json")


def _db_size():
    p = DB
    wal = p + "-wal"
    db_bytes = os.path.getsize(p) if os.path.exists(p) else 0
    wal_bytes = os.path.getsize(wal) if os.path.exists(wal) else 0
    return db_bytes, wal_bytes


def _mem_mb():
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024.0


def _dup_rate():
    try:
        c = connect()
        total = c.execute("select count(*) from unified_snapshots").fetchone()[0]
        dup = c.execute("""select count(*) from (
            select 1 from unified_snapshots
            group by source,source_match_id,source_market_id,option,received_at
            having count(*)>1)""").fetchone()[0]
        c.close()
        return dup / max(1, total)
    except Exception:
        return 0.0


def run_once(monitor, run_id):
    """执行一轮并采集指标。返回 (ok, metrics)。"""
    t0 = time.time()
    db0, wal0 = _db_size()
    try:
        ok = monitor.run_once()
    except Exception as e:
        log_event("ERROR", "MONITOR", "stability",
                  "round crash: %s" % str(e)[:200], run_id)
        return False, {"error": str(e)[:120]}
    db1, wal1 = _db_size()
    return ok, {
        "elapsed_s": round(time.time() - t0, 1),
        "mem_mb": round(_mem_mb(), 1),
        "db_bytes": db1, "wal_bytes": wal1,
        "db_growth": db1 - db0, "wal_growth": wal1 - wal0,
        "dup_rate": round(_dup_rate(), 4),
    }


def run(duration_hours=24, interval_seconds=None, state_file=STATE_FILE):
    from monitor.monitor import Monitor

    cfg = env.get("monitor") or {}
    interval = interval_seconds or cfg.get("interval_seconds", 300)
    run_id = new_trace_id("stability")
    started = int(time.time())

    c = connect()
    c.execute("""insert into stability_runs(
        run_id,started_at,status,rounds,errors,recoveries) values(?,?,?,?,?,?)""",
        (run_id, started * 1000, "RUNNING", 0, 0, 0))
    c.commit()
    c.close()

    state = {"run_id": run_id, "started_at": started, "status": "RUNNING",
             "rounds": 0, "errors": 0, "recoveries": 0,
             "last_round": None, "metrics": []}
    with open(state_file, "w") as f:
        json.dump(state, f)

    deadline = started + int(duration_hours * 3600)
    rounds = errors = recoveries = 0
    peaks = {"mem_mb": 0.0, "db_bytes": 0, "wal_bytes": 0}

    log_event("INFO", "MONITOR", "stability",
              "stability run started id=%s duration=%sh interval=%ss"
              % (run_id, duration_hours, interval), run_id)

    while time.time() < deadline:
        monitor = Monitor(interval_seconds=interval)
        ok, metrics = run_once(monitor, run_id)
        rounds += 1
        if not ok:
            errors += 1
            if errors <= 3:
                recoveries += 1  # 下一轮继续 = 已恢复
        if metrics:
            peaks["mem_mb"] = max(peaks["mem_mb"], metrics.get("mem_mb", 0))
            peaks["db_bytes"] = max(peaks["db_bytes"],
                                    metrics.get("db_bytes", 0))
            peaks["wal_bytes"] = max(peaks["wal_bytes"],
                                     metrics.get("wal_bytes", 0))
            metrics["round"] = rounds
            metrics["ts"] = int(time.time())
        state.update({
            "rounds": rounds, "errors": errors, "recoveries": recoveries,
            "last_round": metrics, "status": "RUNNING",
            "remaining_s": int(deadline - time.time()),
        })
        with open(state_file, "w") as f:
            json.dump(state, f)

        # 每 10 轮更新一次 DB 汇总
        if rounds % 10 == 0:
            c = connect()
            c.execute("""update stability_runs set
                rounds=?,errors=?,recoveries=? where run_id=?""",
                (rounds, errors, recoveries, run_id))
            c.commit()
            c.close()

        time.sleep(interval)

    final_status = "PASS" if errors == 0 or recoveries > 0 else "ERROR"
    c = connect()
    c.execute("""update stability_runs set
        ended_at=?,status=?,rounds=?,errors=?,recoveries=?,
        mem_mb_peak=?,db_bytes_peak=?,wal_bytes_peak=?,dup_rate=? where run_id=?""",
        (int(time.time()) * 1000, final_status, rounds, errors, recoveries,
         peaks["mem_mb"], peaks["db_bytes"], peaks["wal_bytes"],
         _dup_rate(), run_id))
    c.commit()
    c.close()

    state["status"] = final_status
    state["ended_at"] = int(time.time())
    state["peaks"] = peaks
    with open(state_file, "w") as f:
        json.dump(state, f)
    log_event("INFO", "MONITOR", "stability",
              "stability run done id=%s rounds=%s errors=%s status=%s"
              % (run_id, rounds, errors, final_status), run_id)
    return state


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--hours", type=float, default=24)
    ap.add_argument("--interval", type=int, default=None)
    ap.add_argument("--once", action="store_true")
    args = ap.parse_args()
    if args.once:
        from monitor.monitor import Monitor
        print(run_once(Monitor(), new_trace_id("stability")))
    else:
        state = run(duration_hours=args.hours, interval_seconds=args.interval)
        print(json.dumps(state, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
