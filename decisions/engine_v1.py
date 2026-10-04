"""Decision Engine V1 —— 插件调度器(V0.2 P0-6, 规则 13/34/35)。

Core 只负责: 调度 active Decision Plugin -> 持久化。
direction/selection = UNKNOWN 不是缺陷(规则 13): 选边/是否下注由上层
业务模型完成, 不允许为填值而强行加入投资判断逻辑。
"""
import sqlite3
import json
import time
import hashlib
from core import env
from core.log import start, finish, error

DB = env.db_path()
ENGINE_VERSION = "v1"
PIPELINE_VERSION = env.pipeline_version()


def run(cutoff=None, db=None):
    dbfile = db or DB
    log_id = start("DECISION", "strategies_v1")
    _external = hasattr(dbfile, "execute")
    c = dbfile if _external else sqlite3.connect(dbfile)
    c.row_factory = sqlite3.Row

    try:
        if cutoff:
            rows = c.execute("""select * from strategies_v1
                where status='TRIGGERED' and new_time <= ?
                order by id""", (cutoff,)).fetchall()
        else:
            rows = c.execute("""
             select * from strategies_v1
             where status='TRIGGERED'
             order by id""").fetchall()

        from decisions.plugin import active_plugins
        plugins = active_plugins()

        n = 0
        for r in rows:
            evidence = json.loads(r["signals_json"] or "[]")
            res = None
            for plugin in plugins:
                try:
                    res = plugin.evaluate(r)
                except Exception as e:
                    error("DECISION", e)
                    res = None
                if res:
                    break

            status = (res or {}).get("status", "CANDIDATE")
            candidate = (res or {}).get("candidate", 1 if status == "CANDIDATE" else 0)
            direction = (res or {}).get("direction", "UNKNOWN")
            selection = (res or {}).get("selection", "UNKNOWN")

            h = hashlib.sha256(
                repr((r["canonical_match_id"], r["source"],
                      r["market_type"], r["period"],
                      r["old_time"], r["new_time"],
                      r["strategy_name"])).encode()).hexdigest()

            x = c.execute("""insert or ignore into decisions_v1(
             canonical_match_id,source,market_type,period,
             old_time,new_time,strategy_name,status,candidate,
             direction,selection,strategy_id,
             pipeline_version,engine_version,
             evidence_json,decision_hash,created_at)
             values(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
             (r["canonical_match_id"], r["source"],
              r["market_type"], r["period"],
              r["old_time"], r["new_time"],
              r["strategy_name"], status, candidate,
              direction, selection, r["id"],
              PIPELINE_VERSION, ENGINE_VERSION,
              json.dumps(evidence, ensure_ascii=False),
              h, int(time.time() * 1000)))
            n += x.rowcount

        c.commit()
        finish(log_id, "OK", len(rows), n, "DECISION_V1(plugins)完成")
        print("新增DECISION", n)
        for r in c.execute("""select status,count(*)
            from decisions_v1 group by status"""):
            print(*r)
        return n
    except Exception as e:
        c.rollback()
        error("DECISION", e)
        finish(log_id, "ERROR", 0, 0, str(e)[:200])
        raise
    finally:
        if not _external:
            c.close()


if __name__ == "__main__":
    run()
