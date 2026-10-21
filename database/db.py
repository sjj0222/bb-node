import sqlite3, os, time, hashlib, json
from core import env

DB = env.db_path()

os.makedirs(os.path.dirname(DB), exist_ok=True)

# schema 版本: 新库直接创建当前版本, 旧库通过 MIGRATIONS 幂等升级。
# 单一权威来源: 必须与下方 MIGRATIONS 的最高键一致; 新增迁移时同步此
# 常量(不要从 config 读取——配置缺失时不得静默降级建出缺列库, P0-1)。
SCHEMA_VERSION = 11


# 建库后必须存在的关键列(断言用, 防止 DDL/迁移失配)
_REQUIRED_COLUMNS = {
    "unified_snapshots": (
        "odds_raw", "line_quarters", "league_id", "content_hash",
        "time_quality", "superseded"),
    "match_mappings": (
        "evidence", "rule_version", "approval", "valid_from", "valid_to",
        "operator", "note"),
    "collection_runs": (
        "run_type", "pages", "retries", "partial", "records_duplicate",
        "error_code"),
    "stability_runs": ("status_reason",),
}


def _verify_schema(c):
    """迁移完成后断言关键列存在; 缺失即抛错, 不让缺列库带病运行。"""
    missing = []
    for table, cols in _REQUIRED_COLUMNS.items():
        existing = {r[1] for r in c.execute(
            "PRAGMA table_info(%s)" % table)}
        for col in cols:
            if col not in existing:
                missing.append("%s.%s" % (table, col))
    if missing:
        raise RuntimeError(
            "schema 校验失败: 缺少列 %s (迁移链未完整执行?)"
            % ", ".join(missing))


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


V4_TABLES = """
CREATE TABLE IF NOT EXISTS raw_records(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    raw_path TEXT,
    file_bytes INTEGER DEFAULT 0,
    first_seen_ms INTEGER,
    last_seen_ms INTEGER,
    seen_count INTEGER DEFAULT 1,
    parser_status TEXT DEFAULT 'PARSED',
    UNIQUE(source, content_hash)
);

CREATE TABLE IF NOT EXISTS raw_observations(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    observed_at INTEGER NOT NULL,
    ingest_run_id INTEGER,
    file_bytes INTEGER DEFAULT 0,
    UNIQUE(source, content_hash, observed_at)
);

CREATE TABLE IF NOT EXISTS unmapped_records(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source TEXT NOT NULL,
    source_match_id TEXT NOT NULL,
    reason TEXT NOT NULL,
    normalized_json TEXT,
    first_seen_ms INTEGER,
    last_seen_ms INTEGER,
    seen_count INTEGER DEFAULT 1,
    UNIQUE(source, source_match_id, reason)
);
"""


def _migrate_v4(c):
    """V4(Phase 2): RAW 观测历史/未映射落库/采集运行增强列。幂等、非破坏。

    - raw_records: RAW 文件索引(内容寻址, 不可变)
    - raw_observations: 每次抓取到同一 payload 的观测事实(保序)
    - unmapped_records: 未映射记录落库, 不丢弃(规格: 未映射仍可查询)
    - collection_runs 增加 run_type/pages/retries/partial/records_duplicate/error_code
    """
    c.executescript(V4_TABLES)
    for col, decl in (
        ("run_type", "TEXT"),
        ("pages", "INTEGER DEFAULT 0"),
        ("retries", "INTEGER DEFAULT 0"),
        ("partial", "INTEGER DEFAULT 0"),
        ("records_duplicate", "INTEGER DEFAULT 0"),
        ("error_code", "TEXT"),
    ):
        _add_column(c, "collection_runs", col, decl)


V5_TABLES = """
CREATE TABLE IF NOT EXISTS quality_errors(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source TEXT NOT NULL,
    raw_ref TEXT,
    normalized_json TEXT,
    layer TEXT NOT NULL,
    code TEXT NOT NULL,
    message TEXT,
    status TEXT NOT NULL DEFAULT 'open',
    retried_count INTEGER NOT NULL DEFAULT 0,
    ingest_run_id INTEGER,
    first_seen_ms INTEGER,
    last_seen_ms INTEGER,
    UNIQUE(source, raw_ref, code, layer)
);

CREATE INDEX IF NOT EXISTS idx_quality_source ON quality_errors(source);
CREATE INDEX IF NOT EXISTS idx_quality_raw ON quality_errors(raw_ref);
CREATE INDEX IF NOT EXISTS idx_quality_status ON quality_errors(status);
"""


def _migrate_v5(c):
    """V5(Phase 4): 校验错误队列/拒绝表(规格 §7.2)。

    - quality_errors: 结构/语义/时间校验失败的记录, 不静默丢弃,
      保留 raw_ref 与 normalized_json 以便从 RAW 重放。
    """
    c.executescript(V5_TABLES)


V6_TABLES = """
CREATE TABLE IF NOT EXISTS mapping_review_queue(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source TEXT NOT NULL,
    source_match_id TEXT NOT NULL,
    home TEXT,
    away TEXT,
    event_time INTEGER,
    candidates_json TEXT,
    reason TEXT,
    decision TEXT NOT NULL DEFAULT 'pending',
    operator TEXT,
    note TEXT,
    created_ms INTEGER,
    decided_ms INTEGER,
    UNIQUE(source, source_match_id)
);

CREATE INDEX IF NOT EXISTS idx_review_pending
ON mapping_review_queue(decision, created_ms);

CREATE TABLE IF NOT EXISTS mapping_audit(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source TEXT NOT NULL,
    source_match_id TEXT NOT NULL,
    old_canonical_match_id TEXT,
    new_canonical_match_id TEXT,
    action TEXT NOT NULL,
    rule_version TEXT,
    operator TEXT,
    note TEXT,
    created_ms INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_audit_source
ON mapping_audit(source, source_match_id, created_ms);
"""


def _migrate_v6(c):
    """V6(Phase 5): 映射审计/人工审批/下游失效标记(规格 §8.3/8.4)。

    - mapping_review_queue: 人工确认队列(pending/approved/rejected/deferred)
    - mapping_audit: 所有映射变更的可审计历史(R3 修复)
    - match_mappings 增 evidence/rule_version/approval/valid_from/valid_to/
      operator/note
    - unified_snapshots 增 superseded: 映射变更后旧结果标记失效(不删历史)
    """
    c.executescript(V6_TABLES)
    for col, decl in (
        ("evidence", "TEXT"),
        ("rule_version", "TEXT"),
        ("approval", "TEXT DEFAULT 'auto'"),
        ("valid_from", "INTEGER"),
        ("valid_to", "INTEGER"),
        ("operator", "TEXT"),
        ("note", "TEXT"),
    ):
        _add_column(c, "match_mappings", col, decl)
    _add_column(c, "unified_snapshots", "superseded", "INTEGER DEFAULT 0")
    # 既有数据回填: 映射视为创建时生效
    c.execute("""UPDATE match_mappings
                 SET valid_from=COALESCE(valid_from, created_at)
                 WHERE valid_from IS NULL""")
    c.execute("""UPDATE match_mappings
                 SET rule_version=COALESCE(rule_version, 'match-v1')
                 WHERE rule_version IS NULL""")


V7_TABLES = """
CREATE TABLE IF NOT EXISTS main_selections(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    match_id TEXT NOT NULL,
    market_definition_id TEXT NOT NULL,
    period TEXT,
    selection_id TEXT NOT NULL,
    policy_id TEXT NOT NULL,
    policy_version TEXT,
    selected_source_id TEXT,
    selected_quote_ids TEXT,
    candidate_quote_ids TEXT,
    selection_reason_codes TEXT,
    quality_status TEXT,
    data_as_of_time INTEGER,
    selected_at INTEGER NOT NULL,
    UNIQUE(match_id, market_definition_id, period, policy_id)
);

CREATE INDEX IF NOT EXISTS idx_main_match
ON main_selections(match_id, period);
"""


def _migrate_v7(c):
    """V7(Phase 6): 盘口字段规范与主盘口选择器(规格 §5)。

    - unified_snapshots 增 odds_raw(原始赔率保留)/line_quarters(四分之一球
      编码, R1 修复, 只对新数据生效)
    - main_selections: 主盘口选择结果(可解释的派生输出, 非原始字段)
    """
    c.executescript(V7_TABLES)
    _add_column(c, "unified_snapshots", "odds_raw", "TEXT")
    _add_column(c, "unified_snapshots", "line_quarters", "TEXT")


V8_VIEWS = """
CREATE VIEW IF NOT EXISTS latest_unified_quotes AS
SELECT
    u.id AS quote_id,
    u.canonical_match_id,
    u.source,
    u.source_match_id,
    u.market_type,
    u.period,
    u.line,
    u.line_quarters,
    u.side,
    u.option,
    u.odds,
    u.odds_raw,
    u.event_time AS event_time,
    u.received_at AS observed_at,
    u.created_at AS ingested_at,
    u.time_quality,
    u.content_hash,
    u.league_id,
    u.superseded
FROM unified_snapshots u
WHERE u.superseded = 0
  AND u.id = (
    SELECT u2.id FROM unified_snapshots u2
    WHERE u2.canonical_match_id = u.canonical_match_id
      AND u2.source = u.source
      AND u2.market_type = u.market_type
      AND COALESCE(u2.period,'') = COALESCE(u.period,'')
      AND COALESCE(u2.line,-999) = COALESCE(u.line,-999)
      AND u2.superseded = 0
    ORDER BY u2.received_at DESC, u2.id DESC
    LIMIT 1
  );
"""


def _migrate_v8(c):
    """V8(Phase 7): Unified 查询层(规格 §9)。

    - unified_snapshots 增 league_id(按联赛查询)/content_hash(变更检测)/
      time_quality(来源时间缺失标记, 不伪造时间)
    - latest_unified_quotes 视图: 最新值=查询视图(规格 §9.2),
      显式暴露 event_time/observed_at/ingested_at 三态
    """
    _add_column(c, "unified_snapshots", "league_id", "INTEGER")
    _add_column(c, "unified_snapshots", "content_hash", "TEXT")
    _add_column(c, "unified_snapshots", "time_quality", "TEXT DEFAULT 'ok'")
    c.executescript(V8_VIEWS)
    c.execute("""CREATE INDEX IF NOT EXISTS idx_unified_league
                 ON unified_snapshots(league_id, received_at)""")


V9_TABLES = """
CREATE TABLE IF NOT EXISTS events(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source TEXT NOT NULL,
    event_type TEXT NOT NULL,
    entity_key TEXT NOT NULL,
    event_time INTEGER NOT NULL,
    recorded_at INTEGER NOT NULL,
    payload TEXT,
    payload_hash TEXT NOT NULL,
    ingest_run_id TEXT,
    UNIQUE(source, event_type, entity_key, event_time, payload_hash)
);
CREATE INDEX IF NOT EXISTS idx_events_order
ON events(event_time, recorded_at, id);

CREATE TABLE IF NOT EXISTS event_consumers(
    consumer TEXT NOT NULL,
    event_id INTEGER NOT NULL,
    consumed_at INTEGER DEFAULT 0,
    UNIQUE(consumer, event_id)
);

CREATE TABLE IF NOT EXISTS feature_results(
    feature_name TEXT NOT NULL,
    version TEXT NOT NULL,
    match_id TEXT NOT NULL,
    as_of_time INTEGER NOT NULL,
    value TEXT,
    error TEXT,
    computed_at INTEGER NOT NULL,
    UNIQUE(feature_name, version, match_id, as_of_time)
);

CREATE TABLE IF NOT EXISTS feature_errors(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    feature_name TEXT,
    version TEXT,
    match_id TEXT,
    as_of_time INTEGER,
    error TEXT,
    computed_at INTEGER
);

CREATE TABLE IF NOT EXISTS signal_results(
    rule_id TEXT NOT NULL,
    version TEXT NOT NULL,
    match_id TEXT NOT NULL,
    as_of_time INTEGER NOT NULL,
    status TEXT NOT NULL,
    output TEXT,
    reason TEXT,
    computed_at INTEGER NOT NULL,
    UNIQUE(rule_id, version, match_id, as_of_time)
);

CREATE TABLE IF NOT EXISTS rule_regressions(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    rule_id TEXT,
    from_version TEXT,
    to_version TEXT,
    sample_id TEXT,
    output_before TEXT,
    output_after TEXT,
    diff TEXT,
    run_at INTEGER
);

CREATE TABLE IF NOT EXISTS replay_runs(
    run_id TEXT PRIMARY KEY,
    name TEXT,
    mode TEXT,
    start_ms INTEGER,
    end_ms INTEGER,
    version TEXT,
    code_version TEXT,
    started_at INTEGER,
    finished_at INTEGER,
    status TEXT,
    summary TEXT
);

CREATE TABLE IF NOT EXISTS replay_events(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT,
    seq INTEGER,
    event_id INTEGER,
    event_type TEXT,
    entity_key TEXT,
    event_time INTEGER,
    recorded_at INTEGER,
    payload TEXT
);
CREATE INDEX IF NOT EXISTS idx_replay_run
ON replay_events(run_id, seq);

CREATE TABLE IF NOT EXISTS backtest_runs(
    run_id TEXT PRIMARY KEY,
    rule_id TEXT,
    version TEXT,
    train_start INTEGER,
    train_end INTEGER,
    test_start INTEGER,
    test_end INTEGER,
    params TEXT,
    seed TEXT,
    summary TEXT,
    status TEXT,
    created_at INTEGER
);
"""


def _migrate_v9(c):
    """V9(Phase 8-10): 事件/特征/信号/回放/回测(规格 §10-11)。

    - events/event_consumers: 事件引擎(发生时间/记录时间分离, 幂等)
    - feature_results/feature_errors: 特征引擎(as_of 无泄漏, 版本化)
    - signal_results/rule_regressions: 信号引擎(生命周期/规则变更回归)
    - replay_runs/replay_events: 回放(隔离输出, 稳定排序)
    - backtest_runs: 回测(严格时间切分, 可审计)
    """
    c.executescript(V9_TABLES)


V10_TABLES = """
CREATE TABLE IF NOT EXISTS backup_runs(
    run_id TEXT PRIMARY KEY,
    dest TEXT,
    size_bytes INTEGER,
    sha256 TEXT,
    app_version TEXT,
    schema_version INTEGER,
    status TEXT,
    created_at INTEGER
);
"""


def _migrate_v10(c):
    """V10(Phase 11): 备份运行记录(规格 §15 可审计)。"""
    c.executescript(V10_TABLES)


def _migrate_v11(c):
    """V11(Phase 12): 稳定性终态原因留痕(R8 修复)。

    - stability_runs 增 status_reason: 终态判定理由可审计
    """
    _add_column(c, "stability_runs", "status_reason", "TEXT")


MIGRATIONS = {
    2: _migrate_v2,
    3: _migrate_v3,
    4: _migrate_v4,
    5: _migrate_v5,
    6: _migrate_v6,
    7: _migrate_v7,
    8: _migrate_v8,
    9: _migrate_v9,
    10: _migrate_v10,
    11: _migrate_v11,
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

    # 迁移完成后断言关键列齐全(P0-1: 不允许缺列库带病运行)
    _verify_schema(c)
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
