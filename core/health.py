"""Source Health System(V0.2, 规则 13/14)。

每个 Source 记录: UP/DOWN/STALE/DEGRADED/AUTH_ERROR/RATE_LIMIT/
NETWORK_ERROR/INVALID_RESPONSE + last_success/last_attempt/latency/
records/error_count, 并区分 HTTP SUCCESS / DATA SUCCESS / PIPELINE SUCCESS
(规则 14: HTTP 200 不代表数据有效)。
"""
import time
import sqlite3
from core import env

DB = env.db_path()

UP = "UP"
DOWN = "DOWN"
STALE = "STALE"
DEGRADED = "DEGRADED"
AUTH_ERROR = "AUTH_ERROR"
RATE_LIMIT = "RATE_LIMIT"
NETWORK_ERROR = "NETWORK_ERROR"
INVALID_RESPONSE = "INVALID_RESPONSE"
UNKNOWN = "UNKNOWN"


def record(source, *, status=UP, latency_ms=None, records=0,
           error=None, http_ok=False, data_ok=False, pipeline_ok=False,
           stale_after=None):
    """记录一次 Source 采集尝试。"""
    now = int(time.time() * 1000)
    c = sqlite3.connect(DB)
    c.row_factory = sqlite3.Row
    c.execute("""
    INSERT INTO source_health(
        source,status,last_success,last_attempt,latency_ms,records,
        error_count,last_error,http_success,data_success,pipeline_success,
        updated_at)
    VALUES(?,?,?,?,?,?,?,?,?,?,?,?)
    ON CONFLICT(source) DO UPDATE SET
        status=excluded.status,
        last_attempt=excluded.last_attempt,
        last_success=CASE WHEN excluded.last_success IS NOT NULL
            THEN excluded.last_success ELSE source_health.last_success END,
        latency_ms=excluded.latency_ms,
        records=excluded.records,
        error_count=source_health.error_count
            + CASE WHEN excluded.error_count > 0 THEN 1 ELSE 0 END,
        last_error=CASE WHEN excluded.last_error IS NOT NULL
            THEN excluded.last_error ELSE source_health.last_error END,
        http_success=excluded.http_success,
        data_success=excluded.data_success,
        pipeline_success=excluded.pipeline_success,
        updated_at=excluded.updated_at
    """, (
        source, status, now if status == UP else None, now,
        latency_ms, records,
        1 if error else 0, error, http_ok, data_ok, pipeline_ok, now))
    c.commit()
    c.close()


def get(source):
    c = sqlite3.connect(DB)
    c.row_factory = sqlite3.Row
    r = c.execute(
        "select * from source_health where source=?", (source,)).fetchone()
    c.close()
    if r is None:
        return None
    return dict(r)


def list_all():
    c = sqlite3.connect(DB)
    c.row_factory = sqlite3.Row
    rows = c.execute(
        "select * from source_health order by source").fetchall()
    c.close()
    return [dict(r) for r in rows]


def status_of(source, stale_after_seconds=None):
    """综合状态: 无记录=UNKNOWN; 超时未成功=STALE; 否则按记录。"""
    h = get(source)
    if h is None:
        return UNKNOWN
    stale_after_seconds = stale_after_seconds or env.stale_after_seconds()
    now = int(time.time() * 1000)
    if h["last_success"] and now - h["last_success"] > stale_after_seconds * 1000:
        return STALE
    return h["status"]
