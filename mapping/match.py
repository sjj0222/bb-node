import re
import hashlib
import unicodedata
from difflib import SequenceMatcher

def norm_name(s):
    s = str(s or "").strip().lower()
    s = unicodedata.normalize("NFKC", s)
    s = re.sub(r"[\s\-_.·'’]+", "", s)
    s = re.sub(r"[^\w\u4e00-\u9fff]", "", s)
    return s

def name_score(a, b):
    a, b = norm_name(a), norm_name(b)
    if not a or not b:
        return 0.0
    if a == b:
        return 1.0
    return SequenceMatcher(None, a, b).ratio()

def time_score(a, b, tolerance=900):
    if a is None or b is None:
        return 0.0
    try:
        d = abs(int(a) - int(b)) / 1000
    except:
        return 0.0
    if d > tolerance:
        return 0.0
    return max(0.0, 1.0 - d / tolerance)

def make_canonical_id(home, away, event_time):
    key = "%s|%s|%s" % (
        norm_name(home),
        norm_name(away),
        int(event_time or 0) // 60000
    )
    return "cm_" + hashlib.sha256(key.encode()).hexdigest()[:20]

def match_score(a, b):
    hs = name_score(a.home, b.home)
    aws = name_score(a.away, b.away)
    ts = time_score(a.event_time, b.event_time)

    score = hs * 0.4 + aws * 0.4 + ts * 0.2

    if hs == 1 and aws == 1 and ts >= 0.8:
        status = "matched"
    elif score >= 0.88:
        status = "matched"
    elif score >= 0.72:
        status = "possible"
    else:
        status = "unmatched"

    return {
        "status": status,
        "confidence": round(score, 4),
        "home_score": round(hs, 4),
        "away_score": round(aws, 4),
        "time_score": round(ts, 4)
    }

def map_match(a, b):
    r = match_score(a, b)
    if r["status"] == "matched":
        cid = make_canonical_id(
            a.home,
            a.away,
            a.event_time
        )
    else:
        cid = None
    r["canonical_match_id"] = cid
    return r
