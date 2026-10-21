"""Phase 5: 映射审计、人工审批队列与撤销/重算(规格 §8.3/8.4)。

- mapping_audit: 所有映射变更(自动/人工)可审计
- mapping_review_queue: PENDING/CONFLICT 候选进入人工队列
- approve/reject/defer/revoke: 每次操作记录操作者、时间、备注
- 映射变更的下游影响: 旧 unified 结果标记 superseded(不删历史)
"""
import json
import time

from database.db import connect

RULE_VERSION = "match-v1"

_DECISIONS = ("pending", "approved", "rejected", "deferred")


def _now():
    return int(time.time() * 1000)


def log_audit(conn, source, source_match_id, old_cid, new_cid, action,
              rule_version=None, operator="system", note=""):
    """写一条映射审计记录。action: auto_approve/auto_unmap/manual_approve/
    reject/defer/revoke/recompute。"""
    conn.execute("""
        INSERT INTO mapping_audit(
            source, source_match_id, old_canonical_match_id,
            new_canonical_match_id, action, rule_version,
            operator, note, created_ms)
        VALUES(?,?,?,?,?,?,?,?,?)
    """, (source, source_match_id, old_cid, new_cid, action,
          rule_version or RULE_VERSION, operator or "system",
          (note or "")[:500], _now()))


def queue_pending(conn, rec, match_result, candidates):
    """PENDING/CONFLICT 候选进入人工队列(§8.1 步骤 4/5)。

    已决(approved/rejected/deferred)的条目不被打回 pending。
    """
    row = conn.execute(
        "select decision from mapping_review_queue "
        "where source=? and source_match_id=?",
        (rec.source, rec.source_match_id)).fetchone()
    if row and row[0] != "pending":
        return row[0]
    now = _now()
    conn.execute("""
        INSERT INTO mapping_review_queue(
            source, source_match_id, home, away, event_time,
            candidates_json, reason, decision, created_ms)
        VALUES(?,?,?,?,?,?,?, 'pending', ?)
        ON CONFLICT(source, source_match_id) DO UPDATE SET
            home=excluded.home,
            away=excluded.away,
            event_time=excluded.event_time,
            candidates_json=excluded.candidates_json,
            reason=excluded.reason,
            created_ms=excluded.created_ms
    """, (rec.source, rec.source_match_id, rec.home, rec.away,
          rec.event_time,
          json.dumps(candidates, ensure_ascii=False)[:4000],
          match_result.get("status", "PENDING"), now))
    return "pending"


def list_queue(conn, decision="pending", source=None, limit=100):
    sql = "select * from mapping_review_queue where decision=?"
    args = [decision]
    if source:
        sql += " and source=?"
        args.append(source)
    sql += " order by created_ms asc limit %d" % limit
    return [dict(r) for r in conn.execute(sql, args)]


def _queue_row(conn, review_id):
    row = conn.execute(
        "select * from mapping_review_queue where id=?",
        (review_id,)).fetchone()
    if row is None:
        raise ValueError("review id not found: %s" % review_id)
    return row


def approve(conn, review_id, operator="cli", note="", candidate_index=0):
    """人工批准: 选定候选作为 canonical 映射; 记录审计; 旧下游标记失效。"""
    row = _queue_row(conn, review_id)
    candidates = json.loads(row["candidates_json"] or "[]")
    if not candidates:
        raise ValueError("review has no candidates")
    if candidate_index >= len(candidates):
        raise ValueError(
            "candidate index %s out of range (0..%s)"
            % (candidate_index, len(candidates) - 1))
    target = candidates[candidate_index]
    new_cid = target["canonical_match_id"]

    prev = conn.execute(
        "select canonical_match_id from match_mappings "
        "where source=? and source_match_id=?",
        (row["source"], row["source_match_id"])).fetchone()
    old_cid = prev[0] if prev else None

    now = _now()
    conn.execute("""
        INSERT INTO match_mappings(
            source, source_match_id, canonical_match_id,
            home, away, event_time, confidence, status,
            created_at, updated_at, evidence, rule_version,
            approval, valid_from, operator, note)
        VALUES(?,?,?,?,?,?,?, 'MAPPED', ?, ?, ?, ?, 'manual', ?, ?, ?)
        ON CONFLICT(source, source_match_id) DO UPDATE SET
            canonical_match_id=excluded.canonical_match_id,
            home=excluded.home, away=excluded.away,
            event_time=excluded.event_time,
            confidence=excluded.confidence,
            status=excluded.status,
            updated_at=excluded.updated_at,
            evidence=excluded.evidence,
            rule_version=excluded.rule_version,
            approval=excluded.approval,
            valid_to=NULL,
            operator=excluded.operator,
            note=excluded.note
    """, (row["source"], row["source_match_id"], new_cid,
          row["home"], row["away"], row["event_time"],
          target.get("confidence", 0.9), now, now,
          json.dumps({"manual": True, "candidate": target},
                     ensure_ascii=False), RULE_VERSION,
          now, operator, note))

    log_audit(conn, row["source"], row["source_match_id"], old_cid, new_cid,
              "manual_approve", operator=operator, note=note)
    if old_cid and old_cid != new_cid:
        _invalidate_downstream(conn, old_cid)

    # Phase 8: 映射批准事件(§10.1 事件来源之一)
    from event.engine import emit
    emit(conn, source=row["source"], event_type="mapping_approved",
         entity_key="%s:%s" % (row["source"], row["source_match_id"]),
         event_time=now, payload={"review_id": review_id,
                                  "canonical_match_id": new_cid,
                                  "old_canonical_match_id": old_cid},
         persist=False)

    conn.execute("""
        UPDATE mapping_review_queue
        SET decision='approved', operator=?, note=?, decided_ms=?
        WHERE id=?
    """, (operator, note, now, review_id))
    return {"review_id": review_id, "source": row["source"],
            "source_match_id": row["source_match_id"],
            "canonical_match_id": new_cid, "old_canonical_match_id": old_cid}


def reject(conn, review_id, operator="cli", note=""):
    """拒绝: 该源记录保持未映射; 记录审计。"""
    row = _queue_row(conn, review_id)
    now = _now()
    conn.execute("""
        UPDATE mapping_review_queue
        SET decision='rejected', operator=?, note=?, decided_ms=?
        WHERE id=?
    """, (operator, note, now, review_id))
    log_audit(conn, row["source"], row["source_match_id"],
              None, None, "reject", operator=operator, note=note)
    return {"review_id": review_id, "decision": "rejected"}


def defer(conn, review_id, operator="cli", note=""):
    """延后: 保留队列, 不产生决定。"""
    row = _queue_row(conn, review_id)
    now = _now()
    conn.execute("""
        UPDATE mapping_review_queue
        SET decision='deferred', operator=?, note=?, decided_ms=?
        WHERE id=?
    """, (operator, note, now, review_id))
    log_audit(conn, row["source"], row["source_match_id"],
              None, None, "defer", operator=operator, note=note)
    return {"review_id": review_id, "decision": "deferred"}


def revoke(conn, source, source_match_id, operator="cli", note=""):
    """撤销: 现有映射立即失效(valid_to=now); 旧下游 unified 标记失效。"""
    row = conn.execute(
        "select id, canonical_match_id from match_mappings "
        "where source=? and source_match_id=?",
        (source, source_match_id)).fetchone()
    if row is None:
        raise ValueError("mapping not found: %s/%s"
                         % (source, source_match_id))
    old_cid = row["canonical_match_id"]
    now = _now()
    conn.execute("""
        UPDATE match_mappings
        SET valid_to=?, status='REVOKED', approval='revoked',
            operator=?, note=?, updated_at=?
        WHERE id=?
    """, (now, operator, note, now, row["id"]))
    log_audit(conn, source, source_match_id, old_cid, None,
              "revoke", operator=operator, note=note)
    if old_cid:
        _invalidate_downstream(conn, old_cid)
    return {"source": source, "source_match_id": source_match_id,
            "canonical_match_id": old_cid, "revoked_at": now}


def _invalidate_downstream(conn, canonical_match_id):
    """§8.4: 旧结果保留并标记 superseded, 不删除。"""
    conn.execute("""
        UPDATE unified_snapshots SET superseded=1
        WHERE canonical_match_id=? AND superseded=0
    """, (canonical_match_id,))


def recompute(conn, source, source_match_id, operator="cli", note=""):
    """安排版本化重算: 标记受影响下游失效并留审计(重算本体在 Phase 9)。"""
    row = conn.execute(
        "select canonical_match_id from match_mappings "
        "where source=? and source_match_id=?",
        (source, source_match_id)).fetchone()
    cid = row[0] if row else None
    log_audit(conn, source, source_match_id, cid, cid,
              "recompute", operator=operator, note=note)
    if cid:
        _invalidate_downstream(conn, cid)
    return {"source": source, "source_match_id": source_match_id,
            "canonical_match_id": cid, "scheduled": True}


def audit_log(conn, source=None, source_match_id=None, limit=200):
    sql = "select * from mapping_audit"
    args = []
    if source:
        sql += " where source=?"
        args.append(source)
        if source_match_id:
            sql += " and source_match_id=?"
            args.append(source_match_id)
    sql += " order by created_ms desc limit %d" % limit
    return [dict(r) for r in conn.execute(sql, args)]
