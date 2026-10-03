import os
import time
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
    c.commit()
    c.close()


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
