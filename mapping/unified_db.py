import time
from database.db import connect

def init_unified():
    c=connect()
    c.execute("""
    CREATE TABLE IF NOT EXISTS unified_snapshots (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        canonical_match_id TEXT,
        source TEXT NOT NULL,
        bookmaker TEXT,
        source_match_id TEXT NOT NULL,
        source_market_id TEXT NOT NULL,
        market_type TEXT NOT NULL,
        period TEXT,
        line_raw TEXT,
        line REAL,
        side TEXT,
        option TEXT NOT NULL,
        odds REAL,
        event_time INTEGER,
        server_time INTEGER,
        received_at INTEGER NOT NULL,
        raw_ref TEXT,
        created_at INTEGER NOT NULL,
        UNIQUE(
          source,
          source_match_id,
          source_market_id,
          option,
          received_at
        )
    )
    """)
    c.execute("""
    CREATE INDEX IF NOT EXISTS idx_unified_match
    ON unified_snapshots(canonical_match_id,received_at)
    """)
    c.execute("""
    CREATE INDEX IF NOT EXISTS idx_unified_market
    ON unified_snapshots(
      canonical_match_id,market_type,period,line,received_at
    )
    """)
    c.execute("""
    CREATE INDEX IF NOT EXISTS idx_unified_source
    ON unified_snapshots(source,source_match_id,received_at)
    """)
    c.commit()
    c.close()

def save_unified(record, canonical_match_id=None, conn=None):
    now = int(time.time() * 1000)
    own = conn is None
    c = conn or connect()

    # Phase 7: 内容哈希(变更检测/幂等, 规格 §9.2) + 时间质量标记
    content_hash = _content_hash(record, canonical_match_id)
    time_quality = "ok" if getattr(record, "event_time", None) else "approx"

    c.execute("""
    INSERT OR IGNORE INTO unified_snapshots
    (canonical_match_id,source,bookmaker,
     source_match_id,source_market_id,
     market_type,period,line_raw,line,side,
     option,odds,odds_raw,line_quarters,
     event_time,server_time,
     received_at,raw_ref,pipeline_version,
     league_id, content_hash, time_quality, created_at)
    VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
    """,(
        canonical_match_id,
        record.source,
        record.bookmaker,
        record.source_match_id,
        record.source_market_id,
        record.market_type,
        record.period,
        record.line_raw,
        record.line,
        record.side,
        record.option,
        record.odds,
        getattr(record, "odds_raw", None),
        getattr(record, "line_quarters", None),
        record.event_time,
        record.server_time,
        record.received_at,
        record.raw_ref,
        getattr(record, "pipeline_version", None),
        getattr(record, "league_id", None),
        content_hash,
        time_quality,
        now
    ))

    # Phase 8: 内容变化 -> 赔率/盘口线变化事件(§10.1, 幂等)
    if content_hash:
        try:
            prev = c.execute("""
                SELECT content_hash FROM unified_snapshots
                WHERE source=? AND source_match_id=?
                  AND COALESCE(period,'')=COALESCE(?,'')
                  AND COALESCE(line,-999)=COALESCE(?,-999)
                  AND id < last_insert_rowid()
                ORDER BY received_at DESC, id DESC LIMIT 1
            """, (record.source, record.source_match_id,
                  getattr(record, "period", None),
                  getattr(record, "line", None))).fetchone()
            if prev and prev[0] and prev[0] != content_hash:
                from event.engine import emit_quote_change
                emit_quote_change(
                    c, canonical_match_id=canonical_match_id,
                    source=record.source,
                    source_market_id=record.source_market_id,
                    market_type=record.market_type,
                    period=record.period, line=record.line,
                    old_content_hash=prev[0],
                    new_content_hash=content_hash,
                    received_at=record.received_at)
        except Exception:
            # 事件为增强能力, 不得阻断统一快照主链路
            pass

    if own:
        c.commit()
        c.close()


def _content_hash(record, canonical_match_id):
    """内容哈希: 仅内容字段(变更检测/幂等, §9.2)。

    严禁混入 received_at 等每轮必变字段——否则"赔率不变也每轮报变化",
    events 被纯噪声灌满(P1-3)。
    """
    import hashlib
    key = "%s|%s|%s|%s|%s|%s|%s|%s" % (
        canonical_match_id or "",
        getattr(record, "source", ""),
        getattr(record, "source_market_id", ""),
        getattr(record, "market_type", ""),
        getattr(record, "period", ""),
        getattr(record, "line", ""),
        getattr(record, "option", ""),
        getattr(record, "odds", ""),
    )
    return hashlib.sha256(key.encode()).hexdigest()

def get_match(canonical_match_id,limit=500):
    c=connect()
    rows=c.execute("""
    SELECT *
    FROM unified_snapshots
    WHERE canonical_match_id=?
    ORDER BY received_at ASC,id ASC
    LIMIT ?
    """,(canonical_match_id,limit)).fetchall()
    c.close()
    return [dict(x) for x in rows]

def get_market(canonical_match_id,market_type,
               period=None,limit=500):
    c=connect()

    if period is None:
        rows=c.execute("""
        SELECT *
        FROM unified_snapshots
        WHERE canonical_match_id=?
          AND market_type=?
        ORDER BY received_at ASC,id ASC
        LIMIT ?
        """,(canonical_match_id,market_type,limit)).fetchall()
    else:
        rows=c.execute("""
        SELECT *
        FROM unified_snapshots
        WHERE canonical_match_id=?
          AND market_type=?
          AND period=?
        ORDER BY received_at ASC,id ASC
        LIMIT ?
        """,(canonical_match_id,market_type,period,limit)).fetchall()

    c.close()
    return [dict(x) for x in rows]
