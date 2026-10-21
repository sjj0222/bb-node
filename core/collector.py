import os
import time
import sys
import json
import uuid
import dataclasses

from core import env
from database.db import connect, init, data_hash
from core.log import start, finish, error
from sources.registry import get_adapter, enabled_sources
from mapping.service import auto_map
from mapping.market_service import map_and_save
from mapping.unified_service import unify
from mapping.status import MAPPED, UNMAPPED, INVALID, PENDING

VERSION = env.pipeline_version()
PROTOCOL = "1"
NODE_FILE = os.path.join(env.base_dir(), "config", "node.json")


def get_node_id():
    os.makedirs(os.path.dirname(NODE_FILE), exist_ok=True)

    if os.path.exists(NODE_FILE):
        try:
            with open(NODE_FILE, encoding="utf-8") as f:
                x = json.load(f)
            if x.get("node_id"):
                return x["node_id"]
        except Exception:
            pass

    nid = "NODE-" + uuid.uuid4().hex[:16]

    with open(NODE_FILE, "w", encoding="utf-8") as f:
        json.dump({
            "node_id": nid,
            "created_at": int(time.time())
        }, f, ensure_ascii=False, indent=2)

    return nid


NODE_ID = get_node_id()


def _new_run(name, run_type=None):
    c = connect()
    cur = c.execute("""
    INSERT INTO collection_runs(started_at,source,success,run_type)
    VALUES(?,?,0,?)
    """, (int(time.time()), name, run_type))
    run_id = cur.lastrowid
    c.commit()
    c.close()
    return run_id


def _finish_run(run_id, match_count, row_count, success, err=None, meta=None):
    meta = meta or {}
    c = connect()
    c.execute("""
    UPDATE collection_runs
    SET finished_at=?,match_count=?,row_count=?,success=?,error=?,
        pages=?,retries=?,partial=?,error_code=?
    WHERE id=?
    """, (int(time.time()), match_count, row_count,
          int(success), (err or "")[:500],
          meta.get("pages", 0), meta.get("retries", 0),
          int(meta.get("partial", False)),
          (meta.get("error_code") or "")[:50] or None,
          run_id))
    c.commit()
    c.close()


def _ledger_raw(conn, source, content_hash, observed_at, ingest_run_id):
    """RAW 文件落账(规格 4.3 raw_records/raw_observations)。

    - raw_records: 内容寻址索引; 重复出现只增 seen_count, 不改文件
    - raw_observations: 每次抓取到同一 payload 记一条观测(保序保留)
    """
    path = os.path.join(env.raw_dir(source), content_hash + ".json")
    size = os.path.getsize(path) if os.path.exists(path) else 0
    now = int(time.time() * 1000)
    conn.execute("""
        INSERT INTO raw_records(source,content_hash,raw_path,file_bytes,
                                first_seen_ms,last_seen_ms,seen_count,parser_status)
        VALUES(?,?,?,?,?,?,1,'PARSED')
        ON CONFLICT(source,content_hash) DO UPDATE SET
            last_seen_ms=excluded.last_seen_ms,
            seen_count=raw_records.seen_count+1,
            file_bytes=excluded.file_bytes
    """, (source, content_hash, path, size, now, now))
    conn.execute("""
        INSERT OR IGNORE INTO raw_observations(
            source,content_hash,observed_at,ingest_run_id,file_bytes)
        VALUES(?,?,?,?,?)
    """, (source, content_hash, observed_at, ingest_run_id, size))


def _ledger_unmapped(conn, source, source_match_id, reason, rec_json):
    """未映射记录落库(规格: 未映射不可丢弃, 仍可查询)。"""
    now = int(time.time() * 1000)
    conn.execute("""
        INSERT INTO unmapped_records(
            source,source_match_id,reason,normalized_json,
            first_seen_ms,last_seen_ms,seen_count)
        VALUES(?,?,?,?,?,?,1)
        ON CONFLICT(source,source_match_id,reason) DO UPDATE SET
            last_seen_ms=excluded.last_seen_ms,
            seen_count=unmapped_records.seen_count+1
    """, (source, source_match_id, reason,
          json.dumps(rec_json, ensure_ascii=False)[:4000], now, now))


def _process_records(recs, counts, conn, source=None, run_id=None):
    """Normalized -> Match Mapping -> Market Mapping -> Unified。

    counts: mapped/unmapped/invalid/pending/unified
    conn: 共享连接(批量写入, 避免逐行 fsync)
    未映射/无效记录落 unmapped_records(Phase 2, R4)。
    """
    for rec in recs:
        src = source or rec.source
        mm = auto_map(rec, rec, conn=conn)
        cid = mm.get("canonical_match_id")

        if mm.get("status") in (INVALID,):
            counts["invalid"] += 1
            _ledger_unmapped(conn, src, rec.source_match_id, "MATCH_INVALID",
                             dataclasses.asdict(rec))
            continue
        if mm.get("status") in (PENDING, UNMAPPED):
            counts["unmapped"] += 1
            _ledger_unmapped(conn, src, rec.source_match_id,
                             "MATCH_" + mm.get("status", "UNMAPPED"),
                             dataclasses.asdict(rec))
            continue

        mkt = map_and_save(rec, canonical_match_id=cid, conn=conn)

        if mkt.status == MAPPED:
            counts["mapped"] += 1
            unify(rec, cid, conn=conn)
            counts["unified"] += 1
        elif mkt.status == UNMAPPED:
            counts["unmapped"] += 1
            _ledger_unmapped(conn, src, rec.source_match_id,
                             "MARKET_UNMAPPED", dataclasses.asdict(rec))
        else:
            counts["invalid"] += 1
            _ledger_unmapped(conn, src, rec.source_match_id,
                             "MARKET_INVALID", dataclasses.asdict(rec))


def _collect_meta(adapter, run_type=None):
    """读取 adapter 的采集元数据(pages/retries/partial/error_code)。"""
    m = getattr(adapter, "last_collect_meta", None)
    meta = {"pages": 0, "retries": 0, "partial": False,
            "error_code": None, "run_type": run_type}
    if isinstance(m, dict):
        meta["pages"] = int(m.get("pages") or 0)
        meta["retries"] = int(m.get("retries") or 0)
        meta["partial"] = bool(m.get("partial"))
        meta["error_code"] = m.get("error_code")
    return meta


def _merge_meta(total, meta):
    total["pages"] += meta["pages"]
    total["retries"] += meta["retries"]
    total["partial"] = total["partial"] or meta["partial"]
    total["error_code"] = total["error_code"] or meta["error_code"]
    if meta.get("run_type"):
        total["run_type"] = meta["run_type"]
    return total


def collect_source(name, received_at=None):
    """采集单个 Source; 独立失败, 不拖垮其他 Source(规则 3.3)。

    Phase 2(R2/R4): 分页失败标记 partial 并落 collection_runs;
    未映射记录落 unmapped_records; RAW 落 raw_records/raw_observations。
    """
    from core import health
    adapter = get_adapter(name)
    run_type = None
    meta_total = {"pages": 0, "retries": 0, "partial": False,
                  "error_code": None, "run_type": None}
    run_id = _new_run(name)
    log_id = start("COLLECT", name)
    t0 = __import__("time").time()
    counts = {"mapped": 0, "unmapped": 0, "invalid": 0,
              "pending": 0, "unified": 0}
    match_count = 0

    try:
        received_at = received_at or int(time.time() * 1000)
        conn = connect()

        if name == "bb":
            bundles = {}
            run_types = (env.get("sources.bb.run_types")
                         or [{"type": 3, "name": "今日"}])
            for rt in run_types:
                part = adapter.collect(rt.get("type", 3), received_at)
                bundles.update(part)
                run_type = str(rt.get("type"))
                _merge_meta(meta_total, _collect_meta(adapter, run_type))
        else:
            bundles = adapter.fetch(received_at)
            _merge_meta(meta_total, _collect_meta(adapter, run_type))

        if name == "bb":
            for bundle in bundles.values():
                match_count += 1
                raw_ref = bundle.get("raw_ref")
                if raw_ref:
                    _ledger_raw(conn, name, raw_ref, received_at, run_id)
                recs = adapter.normalize(
                    bundle["match"],
                    bundle["received_at"],
                    raw_ref=raw_ref)
                _process_records(recs, counts, conn, source=name, run_id=run_id)
        else:
            for bs in bundles.values():
                match_count += 1
                for bundle in bs:
                    raw_ref = bundle.get("raw_ref")
                    if raw_ref:
                        _ledger_raw(conn, name, raw_ref,
                                    bundle.get("received_at") or received_at,
                                    run_id)
                    recs = adapter.normalize(
                        bundle, raw_ref=raw_ref)
                    _process_records(recs, counts, conn, source=name, run_id=run_id)

        conn.commit()
        conn.close()

        row_count = sum(counts.values())
        _finish_run(run_id, match_count, row_count, True,
                    meta=meta_total)
        finish(log_id, "OK", match_count, counts["unified"],
               "mapped=%s unmapped=%s invalid=%s unified=%s partial=%s" % (
                   counts["mapped"], counts["unmapped"],
                   counts["invalid"], counts["unified"],
                   meta_total["partial"]))
        # V0.2 Source Health(规则 13/14): 成功
        health.record(name, status=health.UP,
                      latency_ms=(time.time() - t0) * 1000,
                      records=counts["unified"],
                      http_ok=True, data_ok=True,
                      pipeline_ok=not meta_total["partial"])

        return {
            "run_id": run_id,
            "source": name,
            "matches": match_count,
            "rows": row_count,
            "mapped": counts["mapped"],
            "unmapped": counts["unmapped"],
            "invalid": counts["invalid"],
            "unified": counts["unified"],
            "partial": meta_total["partial"],
            "pages": meta_total["pages"],
            "retries": meta_total["retries"],
            "success": not meta_total["partial"],
        }

    except Exception as e:
        _finish_run(run_id, match_count, 0, False, str(e),
                    meta=meta_total)
        error("COLLECT", e)
        finish(log_id, "ERROR", match_count, 0, str(e)[:200])
        # V0.2 Source Health(规则 14): HTTP/数据/管道失败区分
        status = health.INVALID_RESPONSE
        msg = str(e)[:300]
        if any(k in msg.lower() for k in ("timeout", "timed out")):
            status = health.NETWORK_ERROR
        elif "403" in msg or "401" in msg or "auth" in msg.lower():
            status = health.AUTH_ERROR
        elif "rate" in msg.lower() or "429" in msg:
            status = health.RATE_LIMIT
        else:
            status = health.DOWN
        health.record(name, status=status,
                      latency_ms=(time.time() - t0) * 1000,
                      records=0, error=msg[:200],
                      http_ok=False, data_ok=False, pipeline_ok=False)
        # 规则 3.3: 单个 Source 失败向上抛, 由 collect() 隔离
        return {
            "run_id": run_id,
            "source": name,
            "matches": match_count,
            "rows": 0,
            "mapped": 0,
            "unmapped": 0,
            "invalid": 0,
            "unified": 0,
            "partial": meta_total["partial"],
            "success": False,
            "error": str(e)[:500],
        }


def collect(sources=None):
    """完整采集: 遍历启用 Source, 每个独立执行(规则 3.3)。"""
    init()
    sources = sources or enabled_sources()
    results = []

    print("=== BB Node Collector ===")
    print("Node:", NODE_ID)

    for name in sources:
        try:
            r = collect_source(name)
        except Exception as e:
            r = {"source": name, "success": False, "error": str(e)[:300]}
        results.append(r)
        print("[%s] %s matches=%s unified=%s" % (
            "OK" if r.get("success") else "FAIL",
            name, r.get("matches", 0), r.get("unified", 0)))

    print("=== 采集完成 ===")
    return results


if __name__ == "__main__":
    collect()
