"""Monitor Alert 系统(V0.2 规则 9)。

结构化 Alert: alert_type / severity / entity / source / message / payload /
monitor_run_id / pipeline_run_id。未来可接 Telegram/Webhook/Email,
但不为通知系统重写核心 Pipeline。
"""
import time
import json
import sqlite3
from core import env

DB = env.db_path()

ALERT_TYPES = (
    "SOURCE_DOWN", "SOURCE_STALE", "MAPPING_CONFLICT", "MAPPING_UNMAPPED",
    "DATA_QUALITY_ERROR", "PIPELINE_ERROR", "P2P_ERROR",
    "MATCH_EVENT", "SIGNAL_TRIGGER", "STRATEGY_TRIGGER", "DECISION_CANDIDATE",
)

SEVERITIES = ("INFO", "WARN", "ERROR", "CRITICAL")


def emit(alert_type, message, *, severity="WARN", entity=None,
         source=None, payload=None, monitor_run_id=None, pipeline_run_id=None):
    """生成一条 Alert。返回 alert id。"""
    assert alert_type in ALERT_TYPES, "unknown alert type: %s" % alert_type
    assert severity in SEVERITIES
    now = int(time.time() * 1000)
    c = sqlite3.connect(DB)
    c.row_factory = sqlite3.Row
    cur = c.execute("""insert into alerts(
        alert_type,severity,entity,source,message,payload,
        monitor_run_id,pipeline_run_id,created_at,status)
        values(?,?,?,?,?,?,?,?,?,?)""",
        (alert_type, severity, entity or "", source or "",
         message, json.dumps(payload, ensure_ascii=False) if payload else "",
         monitor_run_id or "", pipeline_run_id or "", now, "OPEN"))
    c.commit()
    c.close()
    return cur.lastrowid


def list_alerts(limit=50, status=None, alert_type=None):
    c = sqlite3.connect(DB)
    c.row_factory = sqlite3.Row
    q = "select * from alerts where 1=1"
    args = []
    if status:
        q += " and status=?"
        args.append(status)
    if alert_type:
        q += " and alert_type=?"
        args.append(alert_type)
    q += " order by id desc limit ?"
    args.append(limit)
    rows = c.execute(q, args).fetchall()
    c.close()
    return [dict(r) for r in rows]


def close(alert_id):
    c = sqlite3.connect(DB)
    c.row_factory = sqlite3.Row
    c.execute("update alerts set status='CLOSED' where id=?", (alert_id,))
    c.commit()
    c.close()


def open_count():
    c = sqlite3.connect(DB)
    c.row_factory = sqlite3.Row
    n = c.execute(
        "select count(*) from alerts where status='OPEN'").fetchone()[0]
    c.close()
    return n
