import sqlite3,os,time,hashlib,json

BASE=os.path.expanduser("~/bb_node")
DB=os.path.join(BASE,"data","bb.db")

os.makedirs(os.path.dirname(DB),exist_ok=True)

def connect():
    c=sqlite3.connect(DB)
    c.row_factory=sqlite3.Row
    c.execute("PRAGMA journal_mode=WAL")
    c.execute("PRAGMA foreign_keys=ON")
    return c

def init():
    c=connect()

    c.executescript("""
    CREATE TABLE IF NOT EXISTS nodes(
        node_id TEXT PRIMARY KEY,
        created_at INTEGER NOT NULL,
        last_seen INTEGER NOT NULL,
        app_version TEXT,
        protocol_version TEXT
    );

    CREATE TABLE IF NOT EXISTS matches(
        match_id TEXT PRIMARY KEY,
        league_id INTEGER,
        league TEXT,
        begin_time TEXT,
        home TEXT,
        away TEXT,
        source TEXT,
        status TEXT,
        updated_at INTEGER
    );

    CREATE TABLE IF NOT EXISTS markets(
        market_id TEXT PRIMARY KEY,
        match_id TEXT NOT NULL,
        mty TEXT,
        pe TEXT,
        updated_at INTEGER,
        FOREIGN KEY(match_id) REFERENCES matches(match_id)
    );

    CREATE TABLE IF NOT EXISTS collection_runs(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        started_at INTEGER NOT NULL,
        finished_at INTEGER,
        source TEXT,
        match_count INTEGER DEFAULT 0,
        row_count INTEGER DEFAULT 0,
        success INTEGER DEFAULT 0,
        error TEXT
    );

    CREATE TABLE IF NOT EXISTS snapshots(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        collection_run_id INTEGER,
        match_id TEXT NOT NULL,
        market_id TEXT NOT NULL,
        option_index INTEGER NOT NULL,
        option TEXT,
        line TEXT,
        odds TEXT,
        collected_at INTEGER NOT NULL,
        node_id TEXT NOT NULL,
        data_hash TEXT NOT NULL,
        FOREIGN KEY(collection_run_id) REFERENCES collection_runs(id),
        FOREIGN KEY(match_id) REFERENCES matches(match_id),
        FOREIGN KEY(market_id) REFERENCES markets(market_id),
        UNIQUE(node_id,match_id,market_id,option_index,
               collected_at,data_hash)
    );

    CREATE INDEX IF NOT EXISTS idx_snap_match
    ON snapshots(match_id,collected_at);

    CREATE INDEX IF NOT EXISTS idx_snap_market
    ON snapshots(market_id,collected_at);

    CREATE INDEX IF NOT EXISTS idx_snap_time
    ON snapshots(collected_at);

    CREATE INDEX IF NOT EXISTS idx_run_time
    ON collection_runs(started_at);
    """)

    c.commit()
    c.close()

def data_hash(row):
    s=json.dumps(row,ensure_ascii=False,sort_keys=True)
    return hashlib.sha256(s.encode()).hexdigest()

if __name__=="__main__":
    init()
    print("DB OK:",DB)
