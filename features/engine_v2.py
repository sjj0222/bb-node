"""Feature Engine V2 —— 生产版(规则 10)。

对 Event / Unified 数据进行结构化统计描述:
  water_changes / up / down / avg|max|total_delta / direction_balance
  shift_levels / shift_ratio (亚盘档位同步)

仅描述状态, 不做信号判定(规则 10.1: Signal 判定在下一层)。
带 lineage: event_refs 记录本特征对应的 events_v3 id 列表。
"""
import sqlite3
import json
import time
from core import env
from core.log import start, finish, error

DB = env.db_path()
ENGINE_VERSION = "v2"
PIPELINE_VERSION = env.pipeline_version()


def run(cutoff=None, db=None):
    dbfile = db or DB
    log_id = start("FEATURE", "events_v3")
    c = sqlite3.connect(dbfile)
    c.row_factory = sqlite3.Row

    try:
        c.execute("delete from features_v2")

        if cutoff:
            rows = c.execute("""select * from events_v3
                where new_time <= ? order by new_time,id""", (cutoff,)).fetchall()
        else:
            rows = c.execute(
                "select * from events_v3 order by new_time,id").fetchall()

        gs = {}
        for r in rows:
            k = (r["canonical_match_id"], r["source"], r["market_type"],
                 r["period"], r["old_time"], r["new_time"])
            gs.setdefault(k, []).append(r)

        for k, rs in gs.items():
            ds = []
            for r in rs:
                try:
                    ds.append(abs(float(r["new_odds"]) - float(r["old_odds"])))
                except Exception:
                    pass

            wc = len(rs)
            up = sum(r["odds_direction"] == "UP" for r in rs)
            down = sum(r["odds_direction"] == "DOWN" for r in rs)

            # 跨窗口累计 WATER_SHIFT 组数 = 该比赛该盘口的档位同步次数
            # (规则 10: shift_levels 描述档位变化程度, 跨窗口才有意义)
            shifts = c.execute("""select count(*) from event_groups_v3
             where canonical_match_id=? and source=? and market_type=?
             and period=? and group_type='WATER_SHIFT'""",
             (k[0], k[1], k[2], k[3])).fetchone()[0]

            data = {
                "avg_delta": round(sum(ds) / max(1, len(ds)), 5),
                "max_delta": round(max(ds), 5) if ds else 0,
                "total_delta": round(sum(ds), 5),
                "direction_balance": round((up - down) / max(1, wc), 4),
            }

            if k[2] == "asian_handicap":
                levels = max(1, wc // 2)
                data["levels"] = levels
                data["shift_levels"] = shifts
                data["shift_ratio"] = round(shifts / levels, 4)
            else:
                data["outcome_changes"] = wc
                data["shift_levels"] = shifts

            event_refs = json.dumps(
                [r["id"] for r in rs], ensure_ascii=False)

            c.execute("""insert into features_v2(
             canonical_match_id,source,market_type,period,
             old_time,new_time,water_changes,up_count,down_count,
             shift_levels,shift_ratio,avg_delta,max_delta,total_delta,
             direction_balance,line_changes,event_refs,
             pipeline_version,engine_version,feature_json,created_at)
             values(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
             (k[0], k[1], k[2], k[3], k[4], k[5], wc, up, down,
              shifts, data.get("shift_ratio"), data["avg_delta"],
              data["max_delta"], data["total_delta"], data["direction_balance"],
              sum(r["event_type"] == "LINE_CHANGE" for r in rs),
              event_refs, PIPELINE_VERSION, ENGINE_VERSION,
              json.dumps(data, ensure_ascii=False), int(time.time() * 1000)))

        c.commit()
        finish(log_id, "OK", len(rows), len(gs), "FEATURE_V2重建完成")
        print("FEATURE_V2重建完成")
        for r in c.execute("""select market_type,count(*) from features_v2
            group by market_type"""):
            print(*r)
        return len(gs)
    except Exception as e:
        c.rollback()
        error("FEATURE", e)
        finish(log_id, "ERROR", 0, 0, str(e)[:200])
        raise
    finally:
        c.close()


if __name__ == "__main__":
    run()
