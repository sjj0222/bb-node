import sqlite3, os, time, hashlib, json
from core import env

DB = env.db_path()

os.makedirs(os.path.dirname(DB), exist_ok=True)

# schema 版本: 新库直接创建当前版本, 旧库通过 MIGRATIONS 幂等升级
SCHEMA_VERSION = env.schema_version()


def connect(db=None):
    dbfile = db or DB
    if db:
        os.makedirs(os.path.dirname(dbfile) or ".", exist_ok=True)
    c = sqlite3.connect(dbfile)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA journal_mode=WAL")
    c.execute("PRAGMA foreign_keys=ON")
    return c


def _column_exists(c, table, column):
    cols = [r[1] for r in c.execute("PRAGMA table_info(%s)" % table)]
    return column in cols


def _add_column(c, table, column, decl):
    if not _column_exists(c, table, column):
        c.execute("ALTER TABLE %s ADD COLUMN %s %s" % (table, column, decl))


def _migrate_v2(c):
    """V2: lineage 引用、版本追踪、market mapping 状态。幂等。"""
    _add_column(c, "events_v3", "unified_snapshot_id", "INTEGER")
    _add_column(c, "events_v3", "pipeline_version", "TEXT")
    _add_column(c, "events_v3", "engine_version", "TEXT")

    _add_column(c, "features_v2", "event_refs", "TEXT")
    _add_column(c, "features_v2", "pipeline_version", "TEXT")
    _add_column(c, "features_v2", "engine_version", "TEXT")

    _add_column(c, "signals_v1", "feature_id", "INTEGER")
    _add_column(c, "signals_v1", "pipeline_version", "TEXT")
    _add_column(c, "signals_v1", "engine_version", "TEXT")

    _add_column(c, "strategies_v1", "signal_id", "INTEGER")
    _add_column(c, "strategies_v1", "pipeline_version", "TEXT")
    _add_column(c, "strategies_v1", "engine_version", "TEXT")

    _add_column(c, "decisions_v1", "strategy_id", "INTEGER")
    _add_column(c, "decisions_v1", "pipeline_version", "TEXT")
    _add_column(c, "decisions_v1", "engine_version", "TEXT")

    _add_column(c, "pipeline_runs", "pipeline_version", "TEXT")
    _add_column(c, "pipeline_runs", "schema_version", "INTEGER")
    _add_column(c, "pipeline_runs", "engine_versions", "TEXT")
    _add_column(c, "pipeline_runs", "config_version", "TEXT")

    _add_column(c, "market_mappings", "status", "TEXT")
    _add_column(c, "unified_snapshots", "pipeline_version", "TEXT")


V3_TABLES = """
CREATE TABLE IF NOT EXISTS source_health(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source TEXT NOT NULL,
    status TEXT NOT NULL,
    last_success INTEGER,
    last_attempt INTEGER,
    latency_ms REAL,
    records INTEGER DEFAULT 0,
    error_count INTEGER DEFAULT 0,
    last_error TEXT,
    http_success INTEGER DEFAULT 0,
    data_success INTEGER DEFAULT 0,
    pipeline_success INTEGER DEFAULT 0,
    updated_at INTEGER NOT NULL,
    UNIQUE(source)
);

CREATE TABLE IF NOT EXISTS app_logs(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts INTEGER NOT NULL,
    level TEXT NOT NULL,
    module TEXT NOT NULL,
    entity TEXT,
    message TEXT,
    trace_id TEXT,
    created_at INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_applogs_time ON app_logs(ts);
CREATE INDEX IF NOT EXISTS idx_applogs_module ON app_logs(module,ts);

CREATE TABLE IF NOT EXISTS dq_runs(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT,
    pipeline_run_id TEXT,
    window_start INTEGER,
    window_end INTEGER,
    total INTEGER,
    valid INTEGER,
    invalid INTEGER,
    missing INTEGER,
    duplicate INTEGER,
    conflict INTEGER,
    unmapped INTEGER,
    stale INTEGER,
    out_of_order INTEGER,
    score REAL,
    detail TEXT,
    pipeline_version TEXT,
    created_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS monitor_runs(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    monitor_run_id TEXT,
    started_at INTEGER,
    ended_at INTEGER,
    status TEXT,
    interval_seconds INTEGER,
    selected_only INTEGER DEFAULT 0,
    rounds INTEGER DEFAULT 0,
    alerts INTEGER DEFAULT 0,
    errors INTEGER DEFAULT 0,
    last_round_at INTEGER
);

CREATE TABLE IF NOT EXISTS watchlist(
    canonical_match_id TEXT PRIMARY KEY,
    note TEXT,
    added_at INTEGER NOT NULL,
    last_seen INTEGER
);

CREATE TABLE IF NOT EXISTS alerts(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    alert_type TEXT NOT NULL,
    severity TEXT NOT NULL,
    entity TEXT,
    source TEXT,
    message TEXT,
    payload TEXT,
    monitor_run_id TEXT,
    pipeline_run_id TEXT,
    created_at INTEGER NOT NULL,
    status TEXT DEFAULT 'OPEN'
);

CREATE INDEX IF NOT EXISTS idx_alerts_type ON alerts(alert_type,created_at);
CREATE INDEX IF NOT EXISTS idx_alerts_status ON alerts(status);

CREATE TABLE IF NOT EXISTS nodes_v2(
    node_id TEXT PRIMARY KEY,
    protocol_version TEXT NOT NULL,
    software_version TEXT,
    capabilities TEXT,
    last_seen INTEGER NOT NULL,
    status TEXT,
    created_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS sync_runs(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    sync_run_id TEXT,
    peer_node_id TEXT,
    direction TEXT,
    object_type TEXT,
    from_cursor INTEGER,
    to_cursor INTEGER,
    batch_size INTEGER,
    status TEXT,
    conflict INTEGER DEFAULT 0,
    rejected INTEGER DEFAULT 0,
    written INTEGER DEFAULT 0,
    started_at INTEGER,
    ended_at INTEGER,
    protocol_version TEXT
);

CREATE TABLE IF NOT EXISTS strategy_plugins(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    plugin_id TEXT NOT NULL,
    version TEXT,
    name TEXT,
    active INTEGER DEFAULT 1,
    registered_at INTEGER NOT NULL,
    UNIQUE(plugin_id)
);

CREATE TABLE IF NOT EXISTS decision_plugins(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    plugin_id TEXT NOT NULL,
    version TEXT,
    name TEXT,
    active INTEGER DEFAULT 1,
    registered_at INTEGER NOT NULL,
    UNIQUE(plugin_id)
);

CREATE TABLE IF NOT EXISTS backtest_runs_v2(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    replay_id INTEGER,
    strategy_plugin TEXT,
    group_by TEXT,
    sample_count INTEGER,
    trigger_count INTEGER,
    success_count INTEGER,
    failure_count INTEGER,
    success_rate REAL,
    result_distribution TEXT,
    params TEXT,
    created_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS replay_runs_v2(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    replay_hash TEXT UNIQUE,
    filter_json TEXT,
    snapshots INTEGER,
    matches INTEGER,
    start_time INTEGER,
    end_time INTEGER,
    data_version TEXT,
    engine_version TEXT,
    schema_version INTEGER,
    config_version TEXT,
    strategy_version TEXT,
    events INTEGER,
    features INTEGER,
    signals INTEGER,
    strategies INTEGER,
    decisions INTEGER,
    created_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS stability_runs(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT,
    started_at INTEGER,
    ended_at INTEGER,
    rounds INTEGER,
    errors INTEGER,
    recoveries INTEGER,
    mem_mb_peak REAL,
    db_bytes_peak INTEGER,
    wal_bytes_peak INTEGER,
    dup_rate REAL,
    status TEXT
);
"""


def _migrate_v3(c):
    """V3: V0.2 表(Source Health / Logs / DQ / Monitor / P2P / Plugin / BacktestV2)。幂等。"""
    c.executescript(V3_TABLES)


MIGRATIONS = {
    2: _migrate_v2,
    3: _migrate_v3,
}


def init(db=None):
    c = connect(db)

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
    );

    CREATE INDEX IF NOT EXISTS idx_mm_canonical
    ON match_mappings(canonical_match_id);

    CREATE INDEX IF NOT EXISTS idx_mm_event
    ON match_mappings(event_time);

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
        status TEXT DEFAULT 'MAPPED',
        created_at INTEGER NOT NULL,
        updated_at INTEGER NOT NULL,
        UNIQUE(source,source_match_id,source_market_id,option)
    );

    CREATE INDEX IF NOT EXISTS idx_market_canonical
    ON market_mappings(canonical_match_id);

    CREATE INDEX IF NOT EXISTS idx_market_type
    ON market_mappings(market_type,period);

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
        pipeline_version TEXT,
        created_at INTEGER NOT NULL,
        UNIQUE(
          source,
          source_match_id,
          source_market_id,
          option,
          received_at
        )
    );

    CREATE INDEX IF NOT EXISTS idx_unified_match
    ON unified_snapshots(canonical_match_id,received_at);

    CREATE INDEX IF NOT EXISTS idx_unified_market
    ON unified_snapshots(
      canonical_match_id,market_type,period,line,received_at
    );

    CREATE INDEX IF NOT EXISTS idx_unified_source
    ON unified_snapshots(source,source_match_id,received_at);

    CREATE TABLE IF NOT EXISTS events_v3(
        id INTEGER PRIMARY KEY,
        canonical_match_id TEXT,
        source TEXT,
        source_match_id TEXT,
        market_type TEXT,
        period TEXT,
        side TEXT,
        option TEXT,
        old_line_raw TEXT,
        new_line_raw TEXT,
        old_odds REAL,
        new_odds REAL,
        odds_direction TEXT,
        line_direction TEXT,
        line_change_type TEXT,
        event_type TEXT,
        old_time INTEGER,
        new_time INTEGER,
        unified_snapshot_id INTEGER,
        pipeline_version TEXT,
        engine_version TEXT,
        event_hash TEXT UNIQUE,
        created_at INTEGER
    );

    CREATE INDEX IF NOT EXISTS idx_events_v3_match
    ON events_v3(canonical_match_id,new_time);

    CREATE INDEX IF NOT EXISTS idx_events_v3_time
    ON events_v3(new_time);

    CREATE TABLE IF NOT EXISTS event_groups_v3(
        id INTEGER PRIMARY KEY,
        canonical_match_id TEXT,
        source TEXT,
        market_type TEXT,
        period TEXT,
        old_time INTEGER,
        new_time INTEGER,
        group_type TEXT,
        event_count INTEGER,
        detail TEXT,
        group_hash TEXT UNIQUE
    );

    CREATE TABLE IF NOT EXISTS features_v2(
        id INTEGER PRIMARY KEY,
        canonical_match_id TEXT,
        source TEXT,
        market_type TEXT,
        period TEXT,
        old_time INTEGER,
        new_time INTEGER,
        water_changes INTEGER,
        up_count INTEGER,
        down_count INTEGER,
        shift_levels INTEGER,
        shift_ratio REAL,
        avg_delta REAL,
        max_delta REAL,
        total_delta REAL,
        direction_balance REAL,
        line_changes INTEGER,
        event_refs TEXT,
        pipeline_version TEXT,
        engine_version TEXT,
        feature_json TEXT,
        created_at INTEGER
    );

    CREATE INDEX IF NOT EXISTS idx_features_v2_key
    ON features_v2(canonical_match_id,market_type,period,new_time);

    CREATE TABLE IF NOT EXISTS signals_v1(
        id INTEGER PRIMARY KEY,
        canonical_match_id TEXT,
        source TEXT,
        market_type TEXT,
        period TEXT,
        old_time INTEGER,
        new_time INTEGER,
        signal_type TEXT,
        strength REAL,
        feature_id INTEGER,
        pipeline_version TEXT,
        engine_version TEXT,
        feature_json TEXT,
        signal_hash TEXT UNIQUE,
        created_at INTEGER
    );

    CREATE INDEX IF NOT EXISTS idx_signals_v1_time
    ON signals_v1(new_time);

    CREATE TABLE IF NOT EXISTS strategies_v1(
        id INTEGER PRIMARY KEY,
        canonical_match_id TEXT,
        source TEXT,
        market_type TEXT,
        period TEXT,
        old_time INTEGER,
        new_time INTEGER,
        strategy_name TEXT,
        status TEXT,
        direction TEXT,
        selection TEXT,
        bet INTEGER,
        signal_id INTEGER,
        pipeline_version TEXT,
        engine_version TEXT,
        signals_json TEXT,
        strategy_hash TEXT UNIQUE,
        created_at INTEGER
    );

    CREATE TABLE IF NOT EXISTS decisions_v1(
        id INTEGER PRIMARY KEY,
        canonical_match_id TEXT,
        source TEXT,
        market_type TEXT,
        period TEXT,
        old_time INTEGER,
        new_time INTEGER,
        strategy_name TEXT,
        status TEXT,
        candidate INTEGER,
        direction TEXT,
        selection TEXT,
        strategy_id INTEGER,
        pipeline_version TEXT,
        engine_version TEXT,
        evidence_json TEXT,
        decision_hash TEXT UNIQUE,
        created_at INTEGER
    );

    CREATE TABLE IF NOT EXISTS pipeline_runs(
        id INTEGER PRIMARY KEY,
        run_id TEXT,
        stage TEXT,
        source TEXT,
        start_time INTEGER,
        end_time INTEGER,
        status TEXT,
        input_count INTEGER,
        output_count INTEGER,
        message TEXT,
        pipeline_version TEXT,
        schema_version INTEGER,
        engine_versions TEXT,
        config_version TEXT
    );

    CREATE TABLE IF NOT EXISTS replay_runs_v1(
        id INTEGER PRIMARY KEY,
        start_time INTEGER,
        end_time INTEGER,
        rows INTEGER,
        matches INTEGER,
        replay_hash TEXT UNIQUE,
        created_at INTEGER
    );

    CREATE TABLE IF NOT EXISTS replay_events_v1(
        id INTEGER PRIMARY KEY,
        old_time INTEGER,
        new_time INTEGER,
        event_count INTEGER,
        created_at INTEGER,
        replay_hash TEXT UNIQUE
    );

    CREATE TABLE IF NOT EXISTS replay_events_v2(
        id INTEGER PRIMARY KEY,
        old_time INTEGER,
        new_time INTEGER,
        canonical_match_id TEXT,
        source TEXT,
        market_type TEXT,
        period TEXT,
        side TEXT,
        option TEXT,
        old_line_raw TEXT,
        new_line_raw TEXT,
        old_odds REAL,
        new_odds REAL,
        odds_direction TEXT,
        line_direction TEXT,
        line_change_type TEXT,
        event_type TEXT,
        event_hash TEXT UNIQUE,
        created_at INTEGER
    );

    CREATE TABLE IF NOT EXISTS backtest_runs_v1(
        id INTEGER PRIMARY KEY,
        replay_id INTEGER,
        samples INTEGER,
        triggered INTEGER,
        signal_types INTEGER,
        strategy_types INTEGER,
        created_at INTEGER
    );
    """)

    # 幂等迁移
    current = c.execute("PRAGMA user_version").fetchone()[0]
    for ver in sorted(MIGRATIONS):
        if current < ver and ver <= SCHEMA_VERSION:
            MIGRATIONS[ver](c)
            c.execute("PRAGMA user_version=%d" % ver)

    c.commit()
    c.close()


def data_hash(row):
    s = json.dumps(row, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(s.encode()).hexdigest()


if __name__ == "__main__":
    init()
    print("DB OK:", DB)
    c = connect()
    print("schema_version:", c.execute("PRAGMA user_version").fetchone()[0])
    c.close()
