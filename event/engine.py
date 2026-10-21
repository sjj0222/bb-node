"""Phase 8: 事件引擎(规格 §10.1)。

- 事件区分 event_time(事件发生时间) 与 recorded_at(系统记录时间)
- 相同输入重复消费幂等: events UNIQUE(source,event_type,entity_key,
  event_time,payload_hash); consumers UNIQUE(consumer,event_id)
- 消费顺序稳定 tie-breaker: (event_time, recorded_at, event_id)
- 事件来源: 新赛事/赛事时间变更/比分状态/盘口新增/盘口线变化/赔率变化/
  来源异常/映射批准撤销(本阶段先接入赔率变化与映射批准两类真实事件)
"""
import hashlib
import json
import time


def _payload_hash(payload):
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, ensure_ascii=False,
                   default=str).encode()).hexdigest()


def emit(conn, *, source, event_type, entity_key, event_time=None,
         payload=None, recorded_at=None, ingest_run_id=None, persist=True):
    """记录一个事件, 返回是否为新事件(重复输入返回 False, 幂等)。"""
    if event_time is None:
        event_time = int(time.time() * 1000)
    if recorded_at is None:
        recorded_at = int(time.time() * 1000)
    payload = payload or {}
    ph = _payload_hash(payload)
    cur = conn.execute("""
        INSERT OR IGNORE INTO events(
            source, event_type, entity_key, event_time, recorded_at,
            payload, payload_hash, ingest_run_id)
        VALUES(?,?,?,?,?,?,?,?)
    """, (source, event_type, entity_key, event_time, recorded_at,
          json.dumps(payload, ensure_ascii=False), ph, ingest_run_id))
    if persist:
        conn.commit()
    return cur.rowcount == 1


def iter_events(conn, consumer, *, start_ms=None, end_ms=None,
                event_types=None, persist=True):
    """按稳定顺序(事件时间, 记录时间, id)迭代并标记已消费(幂等)。"""
    sql = ("SELECT * FROM events WHERE 1=1")
    args = []
    if start_ms is not None:
        sql += " AND event_time>=?"
        args.append(start_ms)
    if end_ms is not None:
        sql += " AND event_time<=?"
        args.append(end_ms)
    if event_types:
        sql += " AND event_type IN (%s)" % ",".join("?" * len(event_types))
        args.extend(event_types)
    sql += " ORDER BY event_time ASC, recorded_at ASC, id ASC"
    for row in conn.execute(sql, args):
        d = dict(row)
        try:
            d["payload"] = json.loads(d["payload"])
        except (TypeError, ValueError):
            pass
        # 幂等消费标记: 同 consumer 不重复处理同一事件
        cur = conn.execute("""
            INSERT OR IGNORE INTO event_consumers(consumer, event_id)
            VALUES(?,?)
        """, (consumer, d["id"]))
        if cur.rowcount:
            d["consumed"] = True
            if persist:
                conn.commit()
        else:
            d["consumed"] = False
        yield d


def emit_quote_change(conn, *, canonical_match_id, source, source_market_id,
                      market_type, period, line, old_content_hash,
                      new_content_hash, received_at):
    """赔率/盘口线变化事件(内容哈希变化触发, §10.1)。"""
    if old_content_hash == new_content_hash:
        return False
    return emit(conn, source=source, event_type="quote_changed",
                entity_key="%s|%s|%s|%s" % (
                    canonical_match_id or "", source_market_id, market_type,
                    period or ""),
                event_time=received_at,
                payload={
                    "canonical_match_id": canonical_match_id,
                    "source": source,
                    "source_market_id": source_market_id,
                    "market_type": market_type,
                    "period": period,
                    "line": line,
                    "content_hash_before": old_content_hash,
                    "content_hash_after": new_content_hash,
                })
