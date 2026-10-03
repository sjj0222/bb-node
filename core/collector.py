import os
import time
import sys
import json
import uuid

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


def _new_run(name):
    c = connect()
    cur = c.execute("""
    INSERT INTO collection_runs(started_at,source,success)
    VALUES(?,?,0)
    """, (int(time.time()), name))
    run_id = cur.lastrowid
    c.commit()
    c.close()
    return run_id


def _finish_run(run_id, match_count, row_count, success, err=None):
    c = connect()
    c.execute("""
    UPDATE collection_runs
    SET finished_at=?,match_count=?,row_count=?,success=?,error=?
    WHERE id=?
    """, (int(time.time()), match_count, row_count,
          int(success), (err or "")[:500], run_id))
    c.commit()
    c.close()


def _process_records(recs, counts, conn):
    """Normalized -> Match Mapping -> Market Mapping -> Unified。

    counts: mapped/unmapped/invalid/pending/unified
    conn: 共享连接(批量写入, 避免逐行 fsync)
    """
    for rec in recs:
        mm = auto_map(rec, rec, conn=conn)
        cid = mm.get("canonical_match_id")

        if mm.get("status") in (INVALID,):
            counts["invalid"] += 1
            continue
        if mm.get("status") in (PENDING, UNMAPPED):
            counts["unmapped"] += 1
            continue

        mkt = map_and_save(rec, canonical_match_id=cid, conn=conn)

        if mkt.status == MAPPED:
            counts["mapped"] += 1
            unify(rec, cid, conn=conn)
            counts["unified"] += 1
        elif mkt.status == UNMAPPED:
            counts["unmapped"] += 1
        else:
            counts["invalid"] += 1


def collect_source(name, received_at=None):
    """采集单个 Source; 独立失败, 不拖垮其他 Source(规则 3.3)。"""
    adapter = get_adapter(name)
    run_id = _new_run(name)
    log_id = start("COLLECT", name)
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
        else:
            bundles = adapter.fetch(received_at)

        if name == "bb":
            for bundle in bundles.values():
                match_count += 1
                recs = adapter.normalize(
                    bundle["match"],
                    bundle["received_at"],
                    raw_ref=bundle.get("raw_ref"))
                _process_records(recs, counts, conn)
        else:
            for bs in bundles.values():
                match_count += 1
                for bundle in bs:
                    recs = adapter.normalize(
                        bundle, raw_ref=bundle.get("raw_ref"))
                    _process_records(recs, counts, conn)

        conn.commit()
        conn.close()

        row_count = sum(counts.values())
        _finish_run(run_id, match_count, row_count, True)
        finish(log_id, "OK", match_count, counts["unified"],
               "mapped=%s unmapped=%s invalid=%s unified=%s" % (
                   counts["mapped"], counts["unmapped"],
                   counts["invalid"], counts["unified"]))

        return {
            "run_id": run_id,
            "source": name,
            "matches": match_count,
            "rows": row_count,
            "mapped": counts["mapped"],
            "unmapped": counts["unmapped"],
            "invalid": counts["invalid"],
            "unified": counts["unified"],
            "success": True,
        }

    except Exception as e:
        _finish_run(run_id, match_count, 0, False, str(e))
        error("COLLECT", e)
        finish(log_id, "ERROR", match_count, 0, str(e)[:200])
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
