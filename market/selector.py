"""Phase 6: 主盘口选择器(规格 §5.3)。

主盘口不是数据库原始字段, 而是可解释的派生选择结果:
  - 策略显式: 来源优先级 / 新鲜度 / 停盘处理 / 冲突处理
  - 无合格候选时返回 no_selection, 不用猜测填充
  - 输出对象包含 selection_id / policy / 候选与选中引用 / 原因码 /
    quality_status / 时间戳
  - 选择结果落 main_selections, 可追溯重算
"""
import json
import time

from database.db import connect

POLICY_DEFAULT = {
    "policy_id": "main-v1",
    "policy_version": "1",
    # 来源优先级: 越靠前越优先
    "source_priority": ["bb", "sx"],
    # 新鲜度要求(ms); None = 不限制
    "require_fresh_ms": None,
    # 停盘处理: skip(跳过停盘候选) / no_selection(直接放弃)
    "handle_suspended": "skip",
    # 多来源冲突处理: latest_received(取最新) / no_selection(放弃)
    "on_conflict": "latest_received",
    # 无合格候选的默认结果
    "default": "no_selection",
}

REASON_NO_CANDIDATE = "NO_CANDIDATE"
REASON_SUSPENDED_SKIP = "SUSPENDED_SKIP"
REASON_SUSPENDED_ABORT = "SUSPENDED_NO_SELECTION"
REASON_STALE_SKIP = "STALE_SKIP"
REASON_CONFLICT = "CONFLICT_MULTI_SOURCE"
REASON_OK = "OK"


def _is_suspended(row):
    """停盘/无效报价判定: 赔率缺失或为 1.0(不允许当有效报价)。"""
    od = row.get("odds")
    if od is None:
        return True
    try:
        return float(od) <= 1.0
    except (TypeError, ValueError):
        return True


def select_main(conn, match_id, market_definition_id, period="full_time",
                policy=None, persist=True):
    """为 (match, 市场定义, 周期) 选择主盘口报价。返回 §5.3 输出对象。"""
    pol = dict(POLICY_DEFAULT)
    if policy:
        pol.update(policy)
    now = int(time.time() * 1000)
    selection_id = "sel_%s_%s_%s_%s" % (
        match_id, market_definition_id, period, pol["policy_version"])

    rows = conn.execute("""
        SELECT * FROM unified_snapshots
        WHERE canonical_match_id=? AND market_type=? AND period=?
          AND superseded=0
        ORDER BY received_at DESC, id DESC
    """, (match_id, market_definition_id, period)).fetchall()

    reasons = []
    candidates = []
    suspended_seen = False
    for r in rows:
        d = dict(r)
        if _is_suspended(d):
            suspended_seen = True
            if pol["handle_suspended"] == "no_selection":
                reasons.append(REASON_SUSPENDED_ABORT)
                return _selection(selection_id, match_id, market_definition_id,
                                  period, pol, None, [], reasons,
                                  "no_selection", now, conn, persist)
            reasons.append(REASON_SUSPENDED_SKIP)
            continue
        if pol.get("require_fresh_ms"):
            age = now - (d.get("received_at") or 0)
            if age > pol["require_fresh_ms"]:
                reasons.append(REASON_STALE_SKIP)
                continue
        candidates.append(d)

    if not candidates:
        reasons.append(REASON_NO_CANDIDATE)
        return _selection(selection_id, match_id, market_definition_id,
                          period, pol, None, [], reasons,
                          "no_selection", now, conn, persist)

    pri = pol["source_priority"]
    cand_sorted = sorted(candidates, key=lambda d: (
        pri.index(d["source"]) if d.get("source") in pri else len(pri),
        -(d.get("received_at") or 0)))

    selected = cand_sorted[0]
    # 冲突检测: 最高优先来源之外是否还有不同报价
    other_lines = {round((c.get("line") or 0), 4) for c in cand_sorted}
    sel_line = round((selected.get("line") or 0), 4)
    if len(other_lines) > 1 and any(
            round((c.get("line") or 0), 4) != sel_line
            for c in cand_sorted[1:]):
        if pol["on_conflict"] == "no_selection":
            reasons.append(REASON_CONFLICT)
            return _selection(selection_id, match_id, market_definition_id,
                              period, pol, None, [],
                              reasons + [REASON_NO_CANDIDATE],
                              "no_selection", now, conn, persist)
        reasons.append(REASON_CONFLICT)

    reasons.append(REASON_OK)
    return _selection(selection_id, match_id, market_definition_id,
                      period, pol, selected, cand_sorted, reasons,
                      "selected", now, conn, persist, data_as_of=selected)


def _selection(selection_id, match_id, market_definition_id, period, pol,
               selected, candidates, reasons, quality_status, now, conn,
               persist, data_as_of=None):
    out = {
        "selection_id": selection_id,
        "match_id": match_id,
        "market_definition_id": market_definition_id,
        "period": period,
        "selection_policy_id": pol["policy_id"],
        "policy_version": pol["policy_version"],
        "selected_source_id": None,
        "selected_quote_ids": [],
        "candidate_quote_ids": [c["id"] for c in candidates],
        "selection_reason_codes": reasons,
        "quality_status": quality_status,
        "data_as_of_time": (data_as_of or {}).get("received_at"),
        "selected_at": now,
    }
    if selected is not None:
        out["selected_source_id"] = selected.get("source")
        out["selected_quote_ids"] = [selected.get("id")]
        out["data_as_of_time"] = selected.get("received_at")

    if persist:
        _persist(conn, out)
    return out


def _persist(conn, sel):
    conn.execute("""
        INSERT INTO main_selections(
            match_id, market_definition_id, period, selection_id,
            policy_id, policy_version, selected_source_id,
            selected_quote_ids, candidate_quote_ids,
            selection_reason_codes, quality_status,
            data_as_of_time, selected_at)
        VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)
        ON CONFLICT(match_id, market_definition_id, period, policy_id)
        DO UPDATE SET
            selection_id=excluded.selection_id,
            policy_version=excluded.policy_version,
            selected_source_id=excluded.selected_source_id,
            selected_quote_ids=excluded.selected_quote_ids,
            candidate_quote_ids=excluded.candidate_quote_ids,
            selection_reason_codes=excluded.selection_reason_codes,
            quality_status=excluded.quality_status,
            data_as_of_time=excluded.data_as_of_time,
            selected_at=excluded.selected_at
    """, (sel["match_id"], sel["market_definition_id"], sel["period"],
          sel["selection_id"], sel["selection_policy_id"],
          sel["policy_version"], sel["selected_source_id"],
          json.dumps(sel["selected_quote_ids"]),
          json.dumps(sel["candidate_quote_ids"]),
          json.dumps(sel["selection_reason_codes"]),
          sel["quality_status"], sel["data_as_of_time"], sel["selected_at"]))


def latest_selection(conn, match_id, market_definition_id, period="full_time"):
    row = conn.execute("""
        SELECT * FROM main_selections
        WHERE match_id=? AND market_definition_id=? AND period=?
        ORDER BY selected_at DESC LIMIT 1
    """, (match_id, market_definition_id, period)).fetchone()
    if row is None:
        return None
    d = dict(row)
    for k in ("selected_quote_ids", "candidate_quote_ids",
              "selection_reason_codes"):
        if d.get(k):
            try:
                d[k] = json.loads(d[k])
            except (TypeError, ValueError):
                pass
    return d
