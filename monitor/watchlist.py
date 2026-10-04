"""Monitor 选定比赛 Watchlist(V0.2 规则 7/7.1)。

支持: ADD / REMOVE / LIST / STATUS(canonical_match_id 维度)。
"""
import time
import sqlite3
from core import env

DB = env.db_path()


def add(canonical_match_id, note=""):
    now = int(time.time() * 1000)
    c = sqlite3.connect(DB)
    c.row_factory = sqlite3.Row
    c.execute("""insert or replace into watchlist(
        canonical_match_id,note,added_at,last_seen)
        values(?,?,?,?)""",
        (canonical_match_id, note, now, now))
    c.commit()
    c.close()
    return True


def remove(canonical_match_id):
    c = sqlite3.connect(DB)
    c.row_factory = sqlite3.Row
    c.execute("delete from watchlist where canonical_match_id=?",
              (canonical_match_id,))
    c.commit()
    c.close()
    return True


def list_all():
    c = sqlite3.connect(DB)
    c.row_factory = sqlite3.Row
    rows = c.execute("select * from watchlist order by added_at").fetchall()
    c.close()
    return [dict(r) for r in rows]


def status(canonical_match_id=None):
    """STATUS: 返回 watchlist 比赛在 unified/events 中的最新状态。"""
    c = sqlite3.connect(DB)
    c.row_factory = sqlite3.Row
    if canonical_match_id:
        rows = c.execute(
            "select * from watchlist where canonical_match_id=?",
            (canonical_match_id,)).fetchall()
    else:
        rows = c.execute("select * from watchlist").fetchall()
    out = []
    for w in rows:
        cmid = w["canonical_match_id"]
        unified = c.execute(
            """select count(*) n, max(received_at) latest
               from unified_snapshots where canonical_match_id=?""",
            (cmid,)).fetchone()
        events = c.execute(
            "select count(*) from events_v3 where canonical_match_id=?",
            (cmid,)).fetchone()[0]
        sig = c.execute(
            "select count(*) from signals_v1 where canonical_match_id=?",
            (cmid,)).fetchone()[0]
        dec = c.execute(
            "select count(*) from decisions_v1 where canonical_match_id=?",
            (cmid,)).fetchone()[0]
        out.append({
            "canonical_match_id": cmid,
            "note": w["note"],
            "unified": unified["n"],
            "latest_received_at": unified["latest"],
            "events": events,
            "signals": sig,
            "decisions": dec,
        })
    c.close()
    return out


def contains(canonical_match_id):
    c = sqlite3.connect(DB)
    c.row_factory = sqlite3.Row
    r = c.execute(
        "select 1 from watchlist where canonical_match_id=?",
        (canonical_match_id,)).fetchone()
    c.close()
    return r is not None
