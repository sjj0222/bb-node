def parse_line(s):
    if s is None:
        return None
    s_str = str(s).strip().replace(" ", "")
    if not s_str:
        return None
    if s_str.count("/") > 1:
        return None
    if "--" in s_str or "++" in s_str or "+-" in s_str or "-+" in s_str:
        return None
    sign = 1
    if s_str.startswith("+"):
        sign = 1
        s_body = s_str[1:]
    elif s_str.startswith("-"):
        sign = -1
        s_body = s_str[1:]
    else:
        sign = 1
        s_body = s_str
    if not s_body:
        return None
    try:
        if "/" in s_body:
            parts = s_body.split("/")
            if len(parts) != 2:
                return None
            a, b = parts[0], parts[1]
            if a == "" or b == "":
                return None
            if "+" in a or "-" in a or "+" in b or "-" in b:
                return None
            x = float(a)
            y = float(b)
            if x != x or y != y:
                return None
            if x in (float("inf"), float("-inf")) or y in (float("inf"), float("-inf")):
                return None
            x = x * sign
            y = y * sign
            return sorted([x, y])
        else:
            if "+" in s_body or "-" in s_body:
                return None
            x = float(s_body)
            if x != x:
                return None
            if x in (float("inf"), float("-inf")):
                return None
            return [x * sign]
    except Exception:
        return None


def norm(s):
    p = parse_line(s)
    if not p:
        return None
    raw_str = str(s) if s is not None else ""
    return {"raw": raw_str, "legs": p, "depth": sum(abs(x) for x in p) / len(p)}


def compare_line(old, new):
    if old is None or new is None:
        return {"changed": None, "direction": "UNKNOWN", "change_type": "UNKNOWN", "steps": None}
    a = norm(old)
    b = norm(new)
    if not a or not b:
        return {"changed": None, "direction": "UNKNOWN", "change_type": "UNKNOWN", "steps": None}
    old_s = str(old).strip().replace(" ", "")
    new_s = str(new).strip().replace(" ", "")
    if a["legs"] == b["legs"]:
        if "/" in old_s and "/" in new_s:
            old_is_neg = old_s.startswith("-")
            old_is_pos = old_s.startswith("+")
            new_is_neg = new_s.startswith("-")
            new_is_pos = new_s.startswith("+")
            if (old_is_neg and new_is_pos) or (old_is_pos and new_is_neg):
                return {"changed": True, "direction": "CROSS", "change_type": "SIGN_FLIP", "steps": 0}
        return {"changed": False, "direction": "SAME", "change_type": "SAME", "steps": 0}
    x = a["depth"]
    y = b["depth"]
    if x == y:
        return {"changed": True, "direction": "CROSS", "change_type": "SIGN_FLIP", "steps": 0}
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
    return {"changed": True, "direction": d, "change_type": ct, "steps": diff / 0.25}
