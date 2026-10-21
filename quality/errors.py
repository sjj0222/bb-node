"""Phase 4: 校验错误队列/拒绝表(规格 §7.2)。

校验失败的记录写入 quality_errors:
  - 不静默丢弃, 保留 raw_ref(RAW 内容哈希)与 normalized_json
  - 同一 source+raw_ref+code+layer 幂等累计(seen 语义在 message/次数?)
    实际按 retried_count/last_seen 呈现重复出现
可从 RAW 重放: raw_ref 定位 data/raw/<source>/<hash>.json。
"""
import json
import time


def ledger_quality_error(conn, rec, layer, code, message, run_id=None):
    """把一条校验失败落库; 幂等: 同 (source, raw_ref, code, layer) 累计。"""
    now = int(time.time() * 1000)
    raw_ref = getattr(rec, "raw_ref", None) or ""
    conn.execute("""
        INSERT INTO quality_errors(
            source, raw_ref, normalized_json, layer, code, message,
            status, retried_count, ingest_run_id, first_seen_ms, last_seen_ms)
        VALUES(?,?,?,?,?,?, 'open', 0, ?, ?, ?)
        ON CONFLICT(source, raw_ref, code, layer) DO UPDATE SET
            last_seen_ms=excluded.last_seen_ms,
            retried_count=quality_errors.retried_count+1,
            normalized_json=excluded.normalized_json,
            ingest_run_id=excluded.ingest_run_id
    """, (rec.source, raw_ref,
          json.dumps(_rec_dict(rec), ensure_ascii=False)[:4000],
          layer, code, message, run_id, now, now))


def _rec_dict(rec):
    import dataclasses
    try:
        return dataclasses.asdict(rec)
    except Exception:
        return {"source": rec.source, "raw_ref": getattr(rec, "raw_ref", None)}


def raw_path_for(source, raw_ref):
    """RAW 内容寻址文件路径(重放入口)。"""
    from core import env
    import os
    return os.path.join(env.raw_dir(source), raw_ref + ".json")


def open_errors(conn, source=None, layer=None):
    """查询 open 状态错误(错误队列)。"""
    sql = "select * from quality_errors where status='open'"
    args = []
    if source:
        sql += " and source=?"
        args.append(source)
    if layer:
        sql += " and layer=?"
        args.append(layer)
    sql += " order by id desc limit 200"
    return [dict(r) for r in conn.execute(sql, args)]
