import json

from .match import map_match, match_score
from .db import save_mapping, connect
from .status import MAPPED, UNMAPPED, CONFLICT, PENDING, INVALID
from .audit import queue_pending


class _Probe:
    """候选扫描用最小对象(只暴露 home/away/event_time)。"""

    def __init__(self, home, away, event_time):
        self.home = home
        self.away = away
        self.event_time = event_time


def _candidates(conn, rec, limit=3):
    """§8.1 步骤 4: 从已确认映射中生成候选列表(分数+证据)。

    仅当存在接近候选时返回非空; 扫描按 canonical 分组去重。
    """
    rows = conn.execute("""
        SELECT canonical_match_id, home, away, event_time, COUNT(*) c
        FROM match_mappings
        WHERE canonical_match_id IS NOT NULL
        GROUP BY canonical_match_id, home, away, event_time
        ORDER BY c DESC LIMIT 200
    """).fetchall()
    out = []
    for cm, home, away, et, c in rows:
        r = match_score(rec, _Probe(home, away, et))
        if r["status"] in (PENDING, CONFLICT, MAPPED) \
                or r["confidence"] >= 0.4:
            out.append({
                "canonical_match_id": cm,
                "home": home,
                "away": away,
                "event_time": et,
                "confidence": r["confidence"],
                "home_score": r["home_score"],
                "away_score": r["away_score"],
                "time_score": r["time_score"],
                "status": r["status"],
                "reps": c,
            })
    out.sort(key=lambda x: -x["confidence"])
    return out[:limit]


def auto_map(a, b, conn=None):
    r = map_match(a, b)
    own = conn is None
    c = conn or connect()

    data = {
        "source": a.source,
        "source_match_id": a.source_match_id,
        "canonical_match_id": r["canonical_match_id"],
        "home": a.home,
        "away": a.away,
        "event_time": a.event_time,
        "confidence": r["confidence"],
        "status": r["status"],
        "evidence": json.dumps({
            "home_score": r["home_score"],
            "away_score": r["away_score"],
            "time_score": r["time_score"],
            "method": "match-v1",
        }, ensure_ascii=False),
        "rule_version": "match-v1",
    }

    save_mapping(data, conn=c)

    # §8.1 步骤 5/6: 明确歧义(PENDING/CONFLICT)进入人工队列
    if r["status"] in (PENDING, CONFLICT):
        cands = _candidates(c, a)
        queue_pending(c, a, r, cands)

    if own:
        c.commit()
        c.close()
    return data
