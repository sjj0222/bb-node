import time
from database.db import connect

def init_market_mapping():
    c=connect()
    c.execute("""
    CREATE TABLE IF NOT EXISTS market_mappings (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        source TEXT NOT NULL,
        canonical_match_id TEXT,
        source_match_id TEXT NOT NULL,
        source_market_id TEXT NOT NULL,
        market_type TEXT NOT NULL,
        period TEXT,
        line_raw TEXT,
        line REAL,
        side TEXT,
        option TEXT NOT NULL,
        odds REAL,
        created_at INTEGER NOT NULL,
        updated_at INTEGER NOT NULL,
        UNIQUE(source,source_match_id,source_market_id,option)
    )
    """)
    c.execute("""
    CREATE INDEX IF NOT EXISTS idx_market_canonical
    ON market_mappings(canonical_match_id)
    """)
    c.execute("""
    CREATE INDEX IF NOT EXISTS idx_market_type
    ON market_mappings(market_type,period)
    """)
    c.commit()
    c.close()

def save_market(m, canonical_match_id=None, source_match_id=None, conn=None):
    now=int(time.time()*1000)
    own = conn is None
    c = conn or connect()

    c.execute("""
    INSERT INTO market_mappings
    (source,canonical_match_id,source_match_id,source_market_id,
     market_type,period,line_raw,line,side,option,odds,status,
     created_at,updated_at)
    VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
    ON CONFLICT(source,source_match_id,source_market_id,option)
    DO UPDATE SET
      canonical_match_id=excluded.canonical_match_id,
      market_type=excluded.market_type,
      period=excluded.period,
      line_raw=excluded.line_raw,
      line=excluded.line,
      side=excluded.side,
      odds=excluded.odds,
      status=excluded.status,
      updated_at=excluded.updated_at
    """,(
        m.source,
        canonical_match_id,
        source_match_id or "",
        m.source_market_id,
        m.market_type,
        m.period,
        m.line_raw,
        m.line,
        m.side,
        m.option,
        m.odds,
        m.status,
        now,
        now
    ))

    if own:
        c.commit()
        c.close()

def get_markets(canonical_match_id):
    c=connect()
    rows=c.execute("""
    SELECT *
    FROM market_mappings
    WHERE canonical_match_id=?
    ORDER BY market_type,period,line,source_market_id,option
    """,(canonical_match_id,)).fetchall()
    c.close()
    return [dict(x) for x in rows]

def get_source_market(source,source_match_id,source_market_id):
    c=connect()
    rows=c.execute("""
    SELECT *
    FROM market_mappings
    WHERE source=? AND source_match_id=? AND source_market_id=?
    ORDER BY option
    """,(source,str(source_match_id),str(source_market_id))).fetchall()
    c.close()
    return [dict(x) for x in rows]
