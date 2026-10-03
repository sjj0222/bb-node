"""Strategy Engine V1 —— 生产版(规则 12)。

对多个 Signal 组合: 同一窗口内 WATER_SHIFT_STRONG + MULTI_LEVEL_SYNC
-> AH_MULTI_LEVEL_WATER (TRIGGERED)。

不得修改 RAW(规则 12); 带 lineage: signal_id 引用来源信号。
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
    log_id = start("STRATEGY", "signals_v1")
    c = sqlite3.connect(dbfile)
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

        groups = {}
        for r in rows:
            k = (r["canonical_match_id"], r["source"],
                 r["market_type"], r["period"], r["old_time"], r["new_time"])
            groups.setdefault(k, []).append(r)

        n = 0
        for k, rs in groups.items():
            names = {r["signal_type"] for r in rs}

            if "WATER_SHIFT_STRONG" in names and \
                    "MULTI_LEVEL_SYNC" in names:
                mid, src, mt, period, t1, t2 = k
                sj = [{
                    "signal_id": r["id"],
                    "signal_type": r["signal_type"],
                    "strength": r["strength"],
                    "feature_id": r["feature_id"],
                } for r in rs]
                h = hashlib.sha256(
                    repr((k, "AH_MULTI_LEVEL_WATER")).encode()).hexdigest()

                x = c.execute("""insert or ignore into strategies_v1(
                 canonical_match_id,source,market_type,period,
                 old_time,new_time,strategy_name,status,
                 direction,selection,bet,signal_id,
                 pipeline_version,engine_version,signals_json,
                 strategy_hash,created_at)
                 values(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                 (mid, src, mt, period, t1, t2,
                  "AH_MULTI_LEVEL_WATER", "TRIGGERED",
                  None, None, 0, rs[0]["id"],
                  PIPELINE_VERSION, ENGINE_VERSION,
                  json.dumps(sj, ensure_ascii=False),
                  h, int(time.time() * 1000)))
                n += x.rowcount

        c.commit()
        finish(log_id, "OK", len(rows), n, "STRATEGY_V1生成完成")
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
        c.close()


if __name__ == "__main__":
    run()
