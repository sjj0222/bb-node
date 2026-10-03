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
    now=int(time.time()*1000)
    own = conn is None
    c = conn or connect()

    c.execute("""
    INSERT OR IGNORE INTO unified_snapshots
    (canonical_match_id,source,bookmaker,
     source_match_id,source_market_id,
     market_type,period,line_raw,line,side,
     option,odds,event_time,server_time,
     received_at,raw_ref,pipeline_version,created_at)
    VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
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
        record.event_time,
        record.server_time,
        record.received_at,
        record.raw_ref,
        getattr(record, "pipeline_version", None),
        now
    ))

    if own:
        c.commit()
        c.close()

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
