import math


def parse_line(s):
    if s is None:
        return None
    s_orig = str(s)
    s = s_orig.strip().replace(" ", "")
    if not s:
        return None
    # check for invalid patterns
    if s.count('/') > 1:
        return None
    if '--' in s or '++' in s or '+-' in s or '-+' in s:
        return None
    sign = 1
    if s.startswith("+"):
        sign = 1
        s_body = s[1:]
    elif s.startswith("-"):
        sign = -1
        s_body = s[1:]
    else:
        sign = 1
        s_body = s
    if not s_body:
        return None
    try:
        if "/" in s_body:
            parts = s_body.split("/")
            if len(parts) != 2:
                return None
            a, b = parts[0], parts[1]
            if a == '' or b == '':
                return None
            if '+' in a or '-' in a or '+' in b or '-' in b:
                return None
            x, y = float(a), float(b)
            if not math.isfinite(x) or not math.isfinite(y):
                return None
            x, y = x * sign, y * sign
            return sorted([x, y])
        else:
            if '+' in s_body or '-' in s_body:
                return None
            x = float(s_body)
            if not math.isfinite(x):
                return None
            return [x * sign]
    except Exception:
        return None


def norm(s):
    p = parse_line(s)
    if not p:
        return None
    return {
        "raw": str(s),
        "legs": p,
        "depth": sum(abs(x) for x in p) / len(p)
    }


def _mid_from_legs(legs):
    if not legs:
        return 0
    qs = sorted([int(round(x * 4)) for x in legs])
    mid = (qs[0] + qs[1]) // 2 if len(qs) == 2 else qs[0]
    return mid


def compare_line(old, new):
    a = norm(old)
    b = norm(new)

    if not a or not b:
        return {
            "changed": None,
            "direction": "UNKNOWN",
            "change_type": "UNKNOWN",
            "steps": None
        }

    x = a["depth"]
    y = b["depth"]
    ma = _mid_from_legs(a["legs"])
    mb = _mid_from_legs(b["legs"])

    # if legs are equivalent (same normalized legs), not changed
    if a["legs"] == b["legs"]:
        return {
            "changed": False,
            "direction": "SAME",
            "change_type": "SAME",
            "steps": 0
        }

    # mid-based equivalence
    if ma == mb:
        return {
            "changed": False,
            "direction": "SAME",
            "change_type": "SAME",
            "steps": 0
        }

    # sign flip / cross zero
    if ma != 0 and mb != 0 and ((ma > 0) != (mb > 0)):
        return {
            "changed": True,
            "direction": "CROSS",
            "change_type": "SIGN_FLIP",
            "steps": abs(mb - ma) / 4.0
        }

    if y > x:
        d = "DEEPER"
    else:
        d = "SHALLOWER"

    diff = abs(y - x)

    if diff == 0.25:
        ct = "QUARTER_STEP"
    elif diff == 0.5:
        ct = "HALF_STEP"
    else:
        ct = "MULTI_STEP"

    return {
        "changed": True,
        "direction": d,
        "change_type": ct,
        "steps": diff / 0.25
    }


if __name__ == "__main__":
    tests = [
        ("-0.5", "-0.75"),
        ("-1", "-1/1.5"),
        ("-1/1.5", "-1"),
        ("+0.5", "+0.25"),
        ("+0.25", "+0.5"),
        ("0", "-0.5"),
        ("-0.5", "0"),
        ("0.5", "0/0.5"),
        ("0/0.5", "0.5"),
        ("1", "1/1.5"),
        ("1/1.5", "1"),
    ]

    print("=== Asian Line Parser V3.3 ===")

    for old, new in tests:
        r = compare_line(old, new)
        print(
            old, "→", new,
            "|", r
        )
