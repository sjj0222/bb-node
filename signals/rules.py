"""Phase 9: 信号引擎(规格 §10.3)。

- 规则 ID 与版本固定; 输入/阈值/输出/理由可追溯
- 输出为研究信号, 不自动下注
- 生命周期 active / superseded / withdrawn / invalidated
- 规则变更跑回归样本并记录差异, 不得用新规则重写旧信号历史
"""
import json
import time

from features.engine import compute_feature, get_feature

RULES = {}


def define_rule(rule_id, version, inputs, thresholds, output, reason,
                evaluate_fn):
    RULES[rule_id] = {
        "rule_id": rule_id, "version": version, "inputs": inputs,
        "thresholds": thresholds, "output": output, "reason": reason,
        "evaluate_fn": evaluate_fn,
    }
    return RULES[rule_id]


def get_rule(rule_id):
    r = RULES.get(rule_id)
    if r is None:
        raise KeyError("unknown rule: %s" % rule_id)
    return r


def evaluate(conn, rule_id, match_id, as_of_time, persist=True):
    """评估信号并落库(研究信号, 不自动下注)。"""
    rule = get_rule(rule_id)
    now = int(time.time() * 1000)
    try:
        value = rule["evaluate_fn"](conn, match_id, int(as_of_time))
        if value is None:
            status, out, reason = "invalidated", None, "no_data"
        else:
            status, out = "active", value
            reason = rule["reason"]
    except Exception as exc:
        status, out, reason = "invalidated", None, repr(exc)
    conn.execute("""
        INSERT INTO signal_results(
            rule_id, version, match_id, as_of_time, status, output, reason,
            computed_at)
        VALUES(?,?,?,?,?,?,?,?)
        ON CONFLICT(rule_id, version, match_id, as_of_time)
        DO UPDATE SET status=excluded.status, output=excluded.output,
                      reason=excluded.reason,
                      computed_at=excluded.computed_at
    """, (rule_id, rule["version"], match_id, int(as_of_time), status,
          json.dumps(out, ensure_ascii=False) if out is not None else None,
          reason, now))
    if persist:
        conn.commit()
    return {"rule_id": rule_id, "version": rule["version"],
            "match_id": match_id, "as_of_time": int(as_of_time),
            "status": status, "output": out, "reason": reason}


def supersede(conn, rule_id, version, reason="", persist=True):
    """将指定版本信号标记 superseded(生命周期)。"""
    n = conn.execute("""
        UPDATE signal_results SET status='superseded', reason=?
        WHERE rule_id=? AND version=?
    """, (reason or "superseded by newer version", rule_id, version)).rowcount
    if persist:
        conn.commit()
    return n


# ---------- 内置研究信号 ----------

def _suspension_watch(ctx_conn, match_id, as_of):
    """30 分钟内亚盘让球差变化 >10% 时发信号(研究用, 非下注建议)。"""
    before = compute_feature(ctx_conn, "ah_odds_spread", match_id,
                             as_of - 30 * 60 * 1000)
    now_val = compute_feature(ctx_conn, "ah_odds_spread", match_id, as_of)
    if before is None or now_val is None:
        return None
    if abs(before) < 1e-9:
        return None
    delta = (now_val - before) / abs(before)
    return {
        "spread_before": before,
        "spread_now": now_val,
        "delta_pct": round(delta * 100, 3),
        "fired": abs(delta) > 0.10,
    }


define_rule(
    rule_id="suspension_watch",
    version="sw-v1",
    inputs=["ah_odds_spread(T-30m)", "ah_odds_spread(T)"],
    thresholds={"delta_pct_threshold": 10.0},
    output="spread delta > 10% within 30min -> research signal",
    reason="30 分钟内亚盘让球差变化超过 10% 的研究信号(不自动下注)",
    evaluate_fn=_suspension_watch,
)


def run_regression(conn, rule_id, from_version, to_version, samples,
                   persist=True):
    """规则版本变更回归: 同一批样本新旧版本输出差异留痕。"""
    rows = []
    now = int(time.time() * 1000)
    for sample in samples:
        match_id, as_of = sample["match_id"], sample["as_of_time"]
        before = _evaluate_version(conn, rule_id, from_version, match_id, as_of)
        after = _evaluate_version(conn, rule_id, to_version, match_id, as_of)
        conn.execute("""INSERT INTO rule_regressions(
            rule_id, from_version, to_version, sample_id, output_before,
            output_after, diff, run_at)
            VALUES(?,?,?,?,?,?,?,?)""",
                     (rule_id, from_version, to_version,
                      "%s@%d" % (match_id, int(as_of)),
                      json.dumps(before, ensure_ascii=False, default=str),
                      json.dumps(after, ensure_ascii=False, default=str),
                      _diff(before, after), now))
        rows.append({"sample": sample, "before": before, "after": after,
                     "diff": _diff(before, after)})
    if persist:
        conn.commit()
    return rows


def _evaluate_version(conn, rule_id, version, match_id, as_of):
    row = conn.execute("""
        SELECT output, status FROM signal_results
        WHERE rule_id=? AND version=? AND match_id=? AND as_of_time=?
    """, (rule_id, version, match_id, int(as_of))).fetchone()
    if row is None:
        return None
    try:
        return json.loads(row[0]) if row[0] else None
    except (TypeError, ValueError):
        return row[0]


def _diff(before, after):
    if before == after:
        return "SAME"
    return "CHANGED: %s -> %s" % (before, after)
