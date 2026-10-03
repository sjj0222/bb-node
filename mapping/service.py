from .match import map_match
from .db import save_mapping

def auto_map(a, b, conn=None):
    r = map_match(a, b)

    data = {
        "source": a.source,
        "source_match_id": a.source_match_id,
        "canonical_match_id": r["canonical_match_id"],
        "home": a.home,
        "away": a.away,
        "event_time": a.event_time,
        "confidence": r["confidence"],
        "status": r["status"]
    }

    save_mapping(data, conn=conn)
    return data
