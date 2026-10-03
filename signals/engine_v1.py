"""Signal Engine V1 —— 生产版(规则 11)。

Feature 满足明确条件后产生结构化信号:
  WATER_SHIFT_STRONG : shift_levels >= 3
  MULTI_LEVEL_SYNC   : shift_ratio >= 0.8

可解释(规则 11.1): 每条信号携带来源 feature_id 与 feature_json(触发依据)。
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
    log_id = start("SIGNAL", "features_v2")
    c = sqlite3.connect(dbfile)
    c.row_factory = sqlite3.Row

    try:
        if cutoff:
            rows = c.execute("""select * from features_v2
                where new_time <= ? order by new_time,id""", (cutoff,)).fetchall()
        else:
            rows = c.execute(
                "select * from features_v2 order by new_time,id").fetchall()

        n = 0
        for r in rows:
            d = json.loads(r["feature_json"])
            sig = []

            if r["market_type"] == "asian_handicap":
                if d.get("shift_levels", 0) >= 3:
                    sig.append(("WATER_SHIFT_STRONG",
                                min(1, d["shift_levels"] / 5)))

                if d.get("shift_ratio", 0) >= 0.8:
                    sig.append(("MULTI_LEVEL_SYNC",
                                d["shift_ratio"]))

            for typ, strength in sig:
                h = hashlib.sha256(
                    repr((r["canonical_match_id"], r["source"],
                          r["market_type"], r["period"], r["old_time"],
                          r["new_time"], typ)).encode()).hexdigest()

                x = c.execute("""insert or ignore into signals_v1(
                 canonical_match_id,source,market_type,period,
                 old_time,new_time,signal_type,strength,
                 feature_id,pipeline_version,engine_version,
                 feature_json,signal_hash,created_at)
                 values(?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                 (r["canonical_match_id"], r["source"],
                  r["market_type"], r["period"], r["old_time"],
                  r["new_time"], typ, round(strength, 4),
                  r["id"], PIPELINE_VERSION, ENGINE_VERSION,
                  r["feature_json"], h, int(time.time() * 1000)))

                n += x.rowcount

        c.commit()
        finish(log_id, "OK", len(rows), n, "SIGNAL_V1生成完成")
        print("新增SIGNAL", n)
        for r in c.execute("""select signal_type,count(*)
            from signals_v1 group by signal_type"""):
            print(*r)
        return n
    except Exception as e:
        c.rollback()
        error("SIGNAL", e)
        finish(log_id, "ERROR", 0, 0, str(e)[:200])
        raise
    finally:
        c.close()


if __name__ == "__main__":
    run()
