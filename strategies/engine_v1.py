"""Strategy Engine V1 —— 插件调度器(V0.2 P0-6, 规则 12/32/33/72)。

Core 只负责: 分组 signals -> 调度 active Strategy Plugin -> 持久化。
规则逻辑全部在 Plugin 中, 可替换/增加而不修改 Core(规则 72)。
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


def _signal_group_key(r):
    return (r["canonical_match_id"], r["source"],
            r["market_type"], r["period"], r["old_time"], r["new_time"])


def run(cutoff=None, db=None):
    dbfile = db or DB
    log_id = start("STRATEGY", "signals_v1")
    _external = hasattr(dbfile, "execute")
    c = dbfile if _external else sqlite3.connect(dbfile)
    c.row_factory = sqlite3.Row

    try:
        if cutoff:
            rows = c.execute("""select * from signals_v1
                where new_time <= ? order by canonical_match_id,old_time,id""",
                             (cutoff,)).fetchall()
        else:
            rows = c.execute("""
             select * from signals_v1
             order by canonical_match_id,old_time,id""").fetchall()

        from strategies.plugin import active_plugins
        plugins = active_plugins()

        groups = {}
        for r in rows:
            groups.setdefault(_signal_group_key(r), []).append(r)

        n = 0
        for k, rs in groups.items():
            for plugin in plugins:
                try:
                    res = plugin.evaluate(rs)
                except Exception as e:
                    error("STRATEGY", e)
                    res = None
                if not res:
                    continue

                mid, src, mt, period, t1, t2 = k
                sj = res["evidence"].get("signals", [])
                h = hashlib.sha256(
                    repr((k, res["strategy_name"])).encode()).hexdigest()

                x = c.execute("""insert or ignore into strategies_v1(
                 canonical_match_id,source,market_type,period,
                 old_time,new_time,strategy_name,status,
                 direction,selection,bet,signal_id,
                 pipeline_version,engine_version,signals_json,
                 strategy_hash,created_at)
                 values(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                 (mid, src, mt, period, t1, t2,
                  res["strategy_name"], res["status"],
                  res.get("direction"), res.get("selection"),
                  res.get("bet", 0), rs[0]["id"],
                  PIPELINE_VERSION, ENGINE_VERSION,
                  json.dumps(sj, ensure_ascii=False),
                  h, int(time.time() * 1000)))
                n += x.rowcount
                break  # 一个组一个策略即可

        c.commit()
        finish(log_id, "OK", len(rows), n, "STRATEGY_V1(plugins)完成")
        print("新增STRATEGY", n)
        for r in c.execute("""select strategy_name,status,count(*)
            from strategies_v1 group by strategy_name,status"""):
            print(*r)
        return n
    except Exception as e:
        c.rollback()
        error("STRATEGY", e)
        finish(log_id, "ERROR", 0, 0, str(e)[:200])
        raise
    finally:
        if not _external:
            c.close()


if __name__ == "__main__":
    run()
