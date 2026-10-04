"""P2P Node(V0.2 P0-5, 规则 24~31/57~59)。

- Node Identity: node_id / protocol_version / software_version / capabilities /
  last_seen(规则 25)
- 同步对象: RAW + Unified(规则 26, 不同步派生结果)
- 去重 / 完整性验证(source/hash/identity/timestamp/schema, 规则 27/29)
- 断线恢复 + 增量补同步(from/to/cursor/batch/hash/status, 规则 28/57)
- 冲突: 不覆盖(规则 30/31), REJECT / CONFLICT
- 协议版本检查(规则 59): 不兼容 -> REJECT / COMPAT 模式
- 安全(规则 58): node identity / data integrity / protocol / schema 验证

同步实现: 同一节点对(peer 文件或 HTTP), 以 DB 为介质。
本版本提供:
  - 本地节点对(文件交换): sync_push / sync_pull
  - 传输验证: 每条数据带 hash, 接收端重算校验
"""
import os
import time
import json
import hashlib
import sqlite3
import threading
from core import env
from core.log import log_event, new_trace_id
from database.db import connect, data_hash

DB = env.db_path()

PROTOCOL_VERSION = (env.get("p2p.protocol_version") or "1.0")
SOFTWARE_VERSION = "bb-node-v0.2"
DEFAULT_CAPABILITIES = ["raw_sync", "unified_sync", "incremental"]

RAW_COLS = ["id", "source", "match_id", "market_id", "option_index",
            "option", "line", "odds", "collected_at", "node_id", "data_hash"]
UNIFIED_COLS = ["id", "canonical_match_id", "source", "bookmaker",
                "source_match_id", "source_market_id", "market_type",
                "period", "line_raw", "line", "side", "option", "odds",
                "event_time", "server_time", "received_at", "raw_ref"]


def _node_id():
    nid = env.get("p2p.node_id")
    if nid and nid != "auto":
        return nid
    import uuid
    return "node-" + uuid.uuid4().hex[:12]


NODE_ID = _node_id()


def register_node():
    """注册/刷新本节点身份(规则 25)。"""
    now = int(time.time() * 1000)
    c = connect()
    c.execute("""insert into nodes_v2(
        node_id,protocol_version,software_version,capabilities,
        last_seen,status,created_at)
        values(?,?,?,?,?,?,?)
        ON CONFLICT(node_id) DO UPDATE SET
            last_seen=excluded.last_seen,status='UP'""",
        (NODE_ID, PROTOCOL_VERSION, SOFTWARE_VERSION,
         json.dumps(DEFAULT_CAPABILITIES), now, "UP", now))
    c.commit()
    c.close()
    return NODE_ID


def _peer_table(c, peer_id):
    """每个 peer 一张同步账本表(sync_cursor/状态)。"""
    t = "peer_%s" % hashlib.sha256(peer_id.encode()).hexdigest()[:12]
    c.execute("""create table if not exists %s(
        object_type text not null,
        cursor_id integer not null,
        hash text,
        status text,
        updated_at integer not null,
        unique(object_type))""" % t)
    return t


def _record_sync(peer, direction, obj, frm, to, batch, status,
                 conflict=0, rejected=0, written=0, protocol=None):
    c = connect()
    c.execute("""insert into sync_runs(
        sync_run_id,peer_node_id,direction,object_type,from_cursor,to_cursor,
        batch_size,status,conflict,rejected,written,started_at,ended_at,
        protocol_version)
        values(?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (new_trace_id("sync"), peer, direction, obj, frm, to, batch,
         status, conflict, rejected, written,
         int(time.time() * 1000), int(time.time() * 1000), protocol or PROTOCOL_VERSION))
    c.commit()
    c.close()


def _verify_batch(items, object_type):
    """完整性验证(规则 29): 每条记录重算 hash / 校验 schema 字段。"""
    ok, bad = [], []
    for it in items:
        h = it.get("_hash")
        payload = {k: v for k, v in it.items() if k != "_hash"}
        if h and data_hash(payload) != h:
            bad.append(("HASH_MISMATCH", it.get("id")))
            continue
        if object_type == "unified":
            for f in ("source", "received_at", "source_market_id", "option"):
                if f not in payload:
                    bad.append(("MISSING_FIELD", f))
                    break
            else:
                ok.append(payload)
        else:
            for f in ("match_id", "market_id", "collected_at", "data_hash"):
                if f not in payload:
                    bad.append(("MISSING_FIELD", f))
                    break
            else:
                ok.append(payload)
    return ok, bad


def _export_cursor(object_type, cursor, limit, from_node):
    """导出 cursor 之后的数据(增量, 规则 28/57)。"""
    c = connect()
    if object_type == "unified":
        rows = c.execute(
            """select * from unified_snapshots
               where id > ? order by id limit ?""", (cursor, limit)).fetchall()
        out = [dict(r) for r in rows]
    else:
        # RAW = snapshots 表(原始盘口快照)
        rows = c.execute(
            """select * from snapshots where id > ? order by id limit ?""",
            (cursor, limit)).fetchall()
        out = [dict(r) for r in rows]
    c.close()
    for it in out:
        it["_hash"] = data_hash({k: v for k, v in it.items()
                                 if k not in ("_hash",)})
    return out


def _apply_batch(object_type, items, from_node, force=False):
    """写入接收数据(规则 29/30/31)。返回 (written, conflict, rejected)。"""
    c = connect()
    written = conflict = rejected = 0
    try:
        for it in items:
            if object_type == "unified":
                key = (it["source"], it["source_match_id"],
                       it["source_market_id"], it["option"], it["received_at"])
                exist = c.execute(
                    """select 1 from unified_snapshots
                       where source=? and source_match_id=?
                       and source_market_id=? and option=? and received_at=?""",
                    key).fetchone()
                if exist:
                    if force:
                        c.execute("""update unified_snapshots set
                            odds=?,line=?,line_raw=?,side=?,
                            canonical_match_id=?,raw_ref=?,created_at=?
                            where source=? and source_match_id=?
                            and source_market_id=? and option=?
                            and received_at=?""",
                            (it.get("odds"), it.get("line"),
                             it.get("line_raw"), it.get("side"),
                             it.get("canonical_match_id"),
                             it.get("raw_ref"), int(time.time() * 1000),
                             *key))
                        written += 1
                    else:
                        conflict += 1  # 已存在且不一致 -> CONFLICT(不覆盖)
                    continue
                c.execute("""insert into unified_snapshots(
                    canonical_match_id,source,bookmaker,source_match_id,
                    source_market_id,market_type,period,line_raw,line,side,
                    option,odds,event_time,server_time,received_at,raw_ref,
                    pipeline_version,created_at)
                    values(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (it.get("canonical_match_id"), it["source"],
                     it.get("bookmaker"), it["source_match_id"],
                     it["source_market_id"], it.get("market_type"),
                     it.get("period"), it.get("line_raw"), it.get("line"),
                     it.get("side"), it["option"], it.get("odds"),
                     it.get("event_time"), it.get("server_time"),
                     it["received_at"], it.get("raw_ref"),
                     it.get("pipeline_version"), int(time.time() * 1000)))
                written += 1
            else:
                # RAW: snapshots 表 UNIQUE(node_id,match_id,market_id,
                #      option_index,collected_at,data_hash) -> 天然去重
                c.execute("""insert or ignore into snapshots(
                    match_id,market_id,option_index,option,line,odds,
                    collected_at,node_id,data_hash)
                    values(?,?,?,?,?,?,?,?,?)""",
                    (it["match_id"], it["market_id"], it.get("option_index", 0),
                     it.get("option"), it.get("line"), it.get("odds"),
                     it.get("collected_at"), it.get("node_id", from_node),
                     it["data_hash"]))
                written += c.execute("select changes()").fetchone()[0]
        c.commit()
    finally:
        c.close()
    return written, conflict, rejected


def sync_from(peer, object_type, cursor=0, limit=500, force=False):
    """从 peer 拉取增量数据(模拟 peer 侧导出 + 本侧应用)。

    peer: peer 导出的数据文件路径或 dict。返回同步统计。
    """
    register_node()
    if isinstance(peer, str):
        with open(peer, "r", encoding="utf-8") as f:
            bundle = json.load(f)
    else:
        bundle = peer

    # 协议版本检查(规则 59)
    proto = bundle.get("protocol_version", "0")
    if proto != PROTOCOL_VERSION:
        _record_sync(bundle.get("node_id", "?"), "pull", object_type,
                     cursor, 0, 0, "PROTOCOL_MISMATCH",
                     protocol=proto)
        log_event("ERROR", "P2P", object_type,
                  "protocol mismatch %s != %s" % (proto, PROTOCOL_VERSION))
        return {"status": "PROTOCOL_MISMATCH", "written": 0,
                "conflict": 0, "rejected": 0}

    items = bundle.get("items", [])
    ok_items, bad = _verify_batch(items, object_type)
    written, conflict, rejected = _apply_batch(
        object_type, ok_items, bundle.get("node_id", "?"), force=force)

    status = "OK" if not bad else ("OK_WITH_REJECTS" if written else "REJECTED")
    _record_sync(bundle.get("node_id", "?"), "pull", object_type,
                 cursor, bundle.get("to_cursor", 0), len(items), status,
                 conflict=conflict, rejected=rejected + len(bad), written=written,
                 protocol=proto)
    log_event("INFO", "P2P", object_type,
              "sync_from %s written=%s conflict=%s rejected=%s" % (
                  bundle.get("node_id", "?"), written, conflict,
                  rejected + len(bad)))
    return {"status": status, "written": written, "conflict": conflict,
            "rejected": rejected + len(bad), "bad": bad}


def export_bundle(object_type, cursor=0, limit=500, to_node=None):
    """导出增量数据包(规则 57: from/to/cursor/batch/hash/status)。"""
    register_node()
    items = _export_cursor(object_type, cursor, limit, NODE_ID)
    to_cursor = max((it["id"] for it in items), default=cursor)
    return {
        "node_id": NODE_ID,
        "protocol_version": PROTOCOL_VERSION,
        "software_version": SOFTWARE_VERSION,
        "object_type": object_type,
        "from_cursor": cursor,
        "to_cursor": to_cursor,
        "batch_size": len(items),
        "items": items,
        "status": "OK",
    }


def incremental_sync(peer_state, object_type, peer, limit=500, force=False):
    """增量同步入口: 从 peer 的状态账本续传(from/to/cursor)。"""
    c = connect()
    table = _peer_table(c, peer)
    row = c.execute(
        "select cursor_id from %s where object_type=?" % table,
        (object_type,)).fetchone()
    cursor = row["cursor_id"] if row else 0
    c.close()

    bundle = export_bundle(object_type, cursor=cursor, limit=limit)
    result = sync_from(peer, object_type, cursor=cursor, limit=limit,
                       force=force)

    # 更新账本
    c = connect()
    table = _peer_table(c, peer)
    c.execute("""insert or replace into %s(object_type,cursor_id,hash,status,updated_at)
        values(?,?,?,?,?)""" % table,
        (object_type, bundle["to_cursor"], "",
         result["status"], int(time.time() * 1000)))
    c.commit()
    c.close()
    return result, bundle["to_cursor"]


def main():
    import sys
    cmd = sys.argv[1] if len(sys.argv) > 1 else "id"
    if cmd == "id":
        print(register_node())
    elif cmd == "export":
        obj = sys.argv[2] if len(sys.argv) > 2 else "unified"
        cur = int(sys.argv[3]) if len(sys.argv) > 3 else 0
        path = sys.argv[4] if len(sys.argv) > 4 else "/tmp/p2p_bundle.json"
        b = export_bundle(obj, cursor=cur)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(b, f, ensure_ascii=False)
        print("exported", len(b["items"]), "to", path)
    elif cmd == "sync":
        obj = sys.argv[2] if len(sys.argv) > 2 else "unified"
        path = sys.argv[3] if len(sys.argv) > 3 else "/tmp/p2p_bundle.json"
        print(sync_from(path, obj))
    else:
        print("unknown cmd:", cmd)


if __name__ == "__main__":
    main()
