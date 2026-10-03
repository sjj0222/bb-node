import sqlite3
import time
from core import env

DB = env.db_path()

# 显式状态枚举(规则 19): 异常必须显式, 禁止用 None/''/0/UNKNOWN 混用
OK = "OK"
UNMAPPED = "UNMAPPED"
CONFLICT = "CONFLICT"
PENDING = "PENDING"
INVALID = "INVALID"
STALE = "STALE"
ERROR = "ERROR"
UNAVAILABLE = "UNAVAILABLE"
NO_RUN = "NO_RUN"
RUNNING = "RUNNING"

STAGES = [
    "COLLECT",
    "NORMALIZE",
    "MAPPING",
    "UNIFIED",
    "EVENT",
    "FEATURE",
    "SIGNAL",
    "STRATEGY",
    "DECISION"
]

STATUS_OK = {OK, RUNNING}


def health_of(start_time):
    if not start_time:
        return NO_RUN
    age = round((int(time.time() * 1000) - start_time) / 1000, 1)
    state = OK if age <= env.stale_after_seconds() else STALE
    return state, age


def get_status():
    c = sqlite3.connect(DB)
    c.row_factory = sqlite3.Row

    out = []

    for stage in STAGES:
        r = c.execute("""
         select stage,source,status,start_time,end_time,
                input_count,output_count,message,
                pipeline_version,schema_version,engine_versions
         from pipeline_runs
         where stage=?
         order by id desc
         limit 1
        """, (stage,)).fetchone()

        if r:
            duration = None
            if r["end_time"] and r["start_time"]:
                duration = r["end_time"] - r["start_time"]

            health, age = health_of(r["start_time"])
            if r["status"] == RUNNING:
                health = RUNNING

            out.append({
                "stage": r["stage"],
                "source": r["source"],
                "status": r["status"],
                "start_time": r["start_time"],
                "end_time": r["end_time"],
                "duration_ms": duration,
                "age_s": age,
                "health": health,
                "input_count": r["input_count"] or 0,
                "output_count": r["output_count"] or 0,
                "message": r["message"] or "",
                "pipeline_version": r["pipeline_version"],
                "schema_version": r["schema_version"],
                "engine_versions": r["engine_versions"]
            })
        else:
            out.append({
                "stage": stage,
                "source": None,
                "status": NO_RUN,
                "start_time": None,
                "end_time": None,
                "duration_ms": None,
                "age_s": None,
                "health": NO_RUN,
                "input_count": 0,
                "output_count": 0,
                "message": "",
                "pipeline_version": None,
                "schema_version": None,
                "engine_versions": None
            })

    c.close()
    return out


def print_status():
    c = sqlite3.connect(DB)

    r = c.execute(
        "select max(received_at),count(*) from unified_snapshots"
    ).fetchone()

    latest, total = r
    if latest:
        age = round(time.time() - latest / 1000, 1)
        state = "OK" if age <= env.stale_after_seconds() else "STALE"
        print(
            "UNIFIED latest=" + str(latest),
            "rows=" + str(total),
            "age=" + str(age) + "s",
            state
        )
    else:
        print("UNIFIED NO_DATA")

    c.close()

    for r in get_status():
        print(
            r["stage"],
            r["status"],
            r["health"],
            "in=" + str(r["input_count"]),
            "out=" + str(r["output_count"]),
            "age=" + str(r["age_s"]) + "s",
            "ms=" + str(r["duration_ms"])
        )


if __name__ == "__main__":
    print_status()
