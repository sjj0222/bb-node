import time
from database.db import connect

def init_mapping():
    c = connect()
    c.execute("""
    CREATE TABLE IF NOT EXISTS match_mappings (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        source TEXT NOT NULL,
        source_match_id TEXT NOT NULL,
        canonical_match_id TEXT,
        home TEXT,
        away TEXT,
        event_time INTEGER,
        confidence REAL NOT NULL DEFAULT 0,
        status TEXT NOT NULL,
        created_at INTEGER NOT NULL,
        updated_at INTEGER NOT NULL,
        UNIQUE(source, source_match_id)
    )
    """)
    c.execute("""
    CREATE INDEX IF NOT EXISTS idx_mm_canonical
    ON match_mappings(canonical_match_id)
    """)
    c.execute("""
    CREATE INDEX IF NOT EXISTS idx_mm_event
    ON match_mappings(event_time)
    """)
    c.commit()
    c.close()

def save_mapping(r):
    now = int(time.time() * 1000)
    c = connect()
    c.execute("""
    INSERT INTO match_mappings
    (source,source_match_id,canonical_match_id,
     home,away,event_time,confidence,status,
     created_at,updated_at)
    VALUES (?,?,?,?,?,?,?,?,?,?)
    ON CONFLICT(source,source_match_id)
    DO UPDATE SET
      canonical_match_id=excluded.canonical_match_id,
      home=excluded.home,
      away=excluded.away,
      event_time=excluded.event_time,
      confidence=excluded.confidence,
      status=excluded.status,
      updated_at=excluded.updated_at
    """, (
        r["source"],
        r["source_match_id"],
        r.get("canonical_match_id"),
        r.get("home"),
        r.get("away"),
        r.get("event_time"),
        r.get("confidence",0),
        r.get("status","unmatched"),
        now,
        now
    ))
    c.commit()
    c.close()

def get_by_source(source, source_match_id):
    c = connect()
    r = c.execute("""
    SELECT * FROM match_mappings
    WHERE source=? AND source_match_id=?
    """,(source,str(source_match_id))).fetchone()
    c.close()
    return dict(r) if r else None

def get_by_canonical(canonical_match_id):
    c = connect()
    rows = c.execute("""
    SELECT * FROM match_mappings
    WHERE canonical_match_id=?
    ORDER BY source
    """,(canonical_match_id,)).fetchall()
    c.close()
    return [dict(r) for r in rows]

def list_mappings(status=None, limit=100):
    c = connect()
    if status:
        rows=c.execute("""
        SELECT * FROM match_mappings
        WHERE status=?
        ORDER BY updated_at DESC LIMIT ?
        """,(status,limit)).fetchall()
    else:
        rows=c.execute("""
        SELECT * FROM match_mappings
        ORDER BY updated_at DESC LIMIT ?
        """,(limit,)).fetchall()
    c.close()
    return [dict(r) for r in rows]
