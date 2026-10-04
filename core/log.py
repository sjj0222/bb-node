import os
import time
import json
import uuid
import logging
import sqlite3
from core import env

DB = env.db_path()
LOG = env.log_path()

os.makedirs(os.path.dirname(LOG), exist_ok=True)

logging.basicConfig(
    filename=LOG,
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s"
)

_PIPE_VERSION = env.pipeline_version()
_SCHEMA_VERSION = env.schema_version()
_ENGINE_VERSIONS = env.get("engines", {})
_CONFIG_VERSION = os.environ.get("BB_NODE_CONFIG_VERSION", "default")

# V0.2: 日志分层模块(规则 51)
LOG_MODULES = (
    "SOURCE", "COLLECT", "MAPPING", "UNIFIED", "QUALITY",
    "EVENT", "FEATURE", "SIGNAL", "STRATEGY", "DECISION",
    "MONITOR", "P2P", "REPLAY", "BACKTEST",
)


def new_trace_id(prefix="pipeline"):
    """V0.2: trace id(规则 52)。pipeline_run_id / monitor_run_id / replay_run_id / sync_run_id。"""
    return "%s-%s" % (prefix, uuid.uuid4().hex[:12])


def init():
    c = sqlite3.connect(DB)
    c.execute("""create table if not exists pipeline_runs(
        id integer primary key,
        run_id text,
        stage text,
        source text,
        start_time integer,
        end_time integer,
        status text,
        input_count integer,
        output_count integer,
        message text,
        pipeline_version text,
        schema_version integer,
        engine_versions text,
        config_version text
    )""")
    c.execute("""create table if not exists app_logs(
        id integer primary key autoincrement,
        ts integer not null,
        level text not null,
        module text not null,
        entity text,
        message text,
        trace_id text,
        created_at integer not null
    )""")
    c.commit()
    c.close()


def log_event(level, module, entity, message, trace_id=None):
    """V0.2: 结构化分层日志(规则 51/52)。"""
    assert module in LOG_MODULES, "unknown log module: %s" % module
    t = int(time.time() * 1000)
    try:
        c = sqlite3.connect(DB)
        c.execute("""insert into app_logs(ts,level,module,entity,message,trace_id,created_at)
            values(?,?,?,?,?,?,?)""",
            (t, level, module, entity or "", message, trace_id or "", t))
        c.commit()
        c.close()
    except Exception:
        pass
    logging.info("%s | %s | %s | %s | %s",
                 module, level, entity or "", message, trace_id or "")


def start(stage, source=""):
    run_id = str(int(time.time() * 1000))
    t = int(time.time() * 1000)
    c = sqlite3.connect(DB)
    c.execute("""insert into pipeline_runs
        (run_id,stage,source,start_time,status,
         pipeline_version,schema_version,engine_versions,config_version)
        values(?,?,?,?,?,?,?,?,?)""",
        (run_id, stage, source, t, "RUNNING",
         _PIPE_VERSION, _SCHEMA_VERSION,
         __import__("json").dumps(_ENGINE_VERSIONS, ensure_ascii=False),
         _CONFIG_VERSION))
    c.commit()
    c.close()
    logging.info("%s START run=%s source=%s", stage, run_id, source)
    return run_id


def finish(run_id, status="OK", input_count=0,
           output_count=0, message=""):
    t = int(time.time() * 1000)
    c = sqlite3.connect(DB)
    c.execute("""update pipeline_runs
        set end_time=?,status=?,input_count=?,
        output_count=?,message=? where run_id=?""",
        (t, status, input_count, output_count, message, run_id))
    row = c.execute(
        "select stage,source from pipeline_runs where run_id=?",
        (run_id,)).fetchone()
    c.commit()
    c.close()
    stage, source = row if row else ("UNKNOWN", "")
    logging.info(
        "%s END run=%s source=%s status=%s in=%s out=%s %s",
        stage, run_id, source, status, input_count, output_count, message)


def error(stage, e):
    logging.exception("%s ERROR %s", stage, e)


init()
