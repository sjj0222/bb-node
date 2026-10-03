"""Event Engine V3 —— 正式生产版本(规则 9/21/22)。

只描述事实(规则 9.2): LINE_CHANGE / WATER_CHANGE, 不做任何推理。

规则 21 乱序处理: unified_snapshots 按 received_at 排序后取时间点序列,
按时间先后比较相邻时间点(T1<T2<T3...), 输入乱序不会生成错误事件。

规则 9.3: V3 为生产版本, 旧 engine.py / engine_v1.py / engine_v2.py
保留用于历史/审计/Replay 验证, 主 Pipeline 不再调用。
"""
import sqlite3
import time
import hashlib
from core import env
from core.log import start, finish, error

DB = env.db_path()
ENGINE_VERSION = "v3"
PIPELINE_VERSION = env.pipeline_version()


def h(*x):
    s = "|".join("" if v is None else str(v) for v in x)
    return hashlib.sha256(s.encode()).hexdigest()


def _key(r):
    return (r["source"], r["canonical_match_id"], r["market_type"],
            r["period"], r["side"], r["option"])


def compare_window(c, oldt, newt, rows):
    """比较相邻两个时间点, 生成事件。返回 (写入数, 详情列表)。"""
    from events.line import compare_line

    A = [r for r in rows if r["received_at"] == oldt]
    B = [r for r in rows if r["received_at"] == newt]

    old = {}
    for r in A:
        old.setdefault(_key(r), []).append(r)

    n = 0
    details = []
    for r in B:
        k = _key(r)
        cand = old.get(k, [])
        if not cand:
            continue
        a = min(cand, key=lambda x: abs((x["line"] or 0) - (r["line"] or 0)))
        od = a["odds"] != r["odds"]
        lc = str(a["line_raw"]) != str(r["line_raw"])
        info = compare_line(a["line_raw"], r["line_raw"]) if lc else None
        events = []
        if od:
            events.append(("WATER_CHANGE", None))
        if info and info["changed"]:
            events.append(("LINE_CHANGE", info))

        for typ, li in events:
            d = None
            if od:
                d = "UP" if r["odds"] > a["odds"] else "DOWN"
            eh = h(r["canonical_match_id"], r["source"], k,
                   a["line_raw"], r["line_raw"], a["odds"], r["odds"],
                   oldt, newt, typ)
            x = c.execute("""insert or ignore into events_v3
            (canonical_match_id,source,source_match_id,market_type,period,side,
             option,old_line_raw,new_line_raw,old_odds,new_odds,odds_direction,
             line_direction,line_change_type,event_type,old_time,new_time,
             unified_snapshot_id,pipeline_version,engine_version,
             event_hash,created_at)
            values(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (r["canonical_match_id"], r["source"], r["source_match_id"],
             r["market_type"], r["period"], r["side"], r["option"],
             a["line_raw"], r["line_raw"], a["odds"], r["odds"], d,
             li["direction"] if li else None,
             li["change_type"] if li else None,
             typ, oldt, newt, r["id"],
             PIPELINE_VERSION, ENGINE_VERSION,
             eh, int(time.time() * 1000)))
            if x.rowcount:
                n += 1
                details.append(typ)

    return n, details


def run(cutoff=None, db=None):
    """生产入口。cutoff: 毫秒时间戳, 只处理 <= cutoff 的快照(时间旅行)。"""
    dbfile = db or DB
    log_id = start("EVENT", "unified")
    c = sqlite3.connect(dbfile)
    c.row_factory = sqlite3.Row

    try:
        if cutoff:
            rows = c.execute("""select * from unified_snapshots
                where canonical_match_id is not null
                  and received_at <= ?
                order by received_at,id""", (cutoff,)).fetchall()
        else:
            rows = c.execute("""select * from unified_snapshots
                where canonical_match_id is not null
                order by received_at,id""").fetchall()

        ts = sorted(set(r["received_at"] for r in rows))
        if len(ts) < 2:
            finish(log_id, "OK", len(rows), 0, "需要至少2个时间点")
            print("需要至少2个时间点")
            return 0, []

        total = 0
        pairs = []

        # 规则 21/22: 按 source 分组, 各组内按时间排序比较相邻时间点
        # (不同 source 采集时间独立, 不得跨 source 比较)
        by_source = {}
        for r in rows:
            by_source.setdefault(r["source"], []).append(r)

        for src, srows in by_source.items():
            ts = sorted(set(r["received_at"] for r in srows))
            for oldt, newt in zip(ts, ts[1:]):
                n, details = compare_window(c, oldt, newt, srows)
                total += n
                pairs.append((src, oldt, newt, n, details))
                if n:
                    print("WINDOW", src, oldt, "->", newt, "EVENTS", n)

        c.commit()
        finish(log_id, "OK", len(rows), total,
               "windows=%d" % len(pairs))
        print("新增事件", total)
        for x in c.execute(
                "select event_type,count(*) n from events_v3 group by event_type"):
            print(x["event_type"], x["n"])
        return total, pairs
    except Exception as e:
        c.rollback()
        error("EVENT", e)
        finish(log_id, "ERROR", 0, 0, str(e)[:200])
        raise
    finally:
        c.close()


def main():
    run()


if __name__ == "__main__":
    main()
