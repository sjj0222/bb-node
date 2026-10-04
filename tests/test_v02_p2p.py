"""V0.2 测试矩阵 4: P2P(规则 69)。

覆盖: Node Identity、正常同步、去重、hash 完整性、冲突(不覆盖)、
非法数据 REJECT、协议版本不匹配、增量补同步。
RAW 同步对象 = 原样 raw 文件(规则 4/26, data/raw/<source>/<hash>.json)。
"""
import json
import os
import time

import pytest

from p2p import node as p2p
from core import env
from database.db import connect, data_hash


def _raw_file(node, i, content=None, t=None):
    """构造一条 raw 文件记录 {source, raw_id, data_hash, content, collected_at}。"""
    t = t or int(time.time() * 1000) + i
    content = content or json.dumps({"src": node, "i": i, "t": t},
                                    ensure_ascii=False)
    h = data_hash(content)
    return {
        "source": node,
        "raw_id": h,
        "data_hash": h,
        "content": content,
        "collected_at": t,
    }


def _seed_raw_files(n, node="node-a", start=None):
    """在本地 raw 目录写 n 个 raw 文件。"""
    start = start if start is not None else int(time.time() * 1000)
    d = env.raw_dir(node)
    os.makedirs(d, exist_ok=True)
    for i in range(n):
        it = _raw_file(node, i, t=start + i * 1000)
        fn = os.path.join(d, "%s.json" % it["data_hash"])
        with open(fn, "w", encoding="utf-8") as f:
            f.write(it["content"])
        os.utime(fn, (it["collected_at"] / 1000, it["collected_at"] / 1000))
    return n


def _bundle(items, node="node-b", obj="raw"):
    out = []
    for it in items:
        p = {k: v for k, v in it.items() if k != "_hash"}
        out.append(dict(p, _hash=data_hash(p)))
    return {"node_id": node, "protocol_version": p2p.PROTOCOL_VERSION,
            "object_type": obj, "from_cursor": 0,
            "to_cursor": len(out), "items": out, "status": "OK"}


def _local_raw_count(node=None):
    base = os.path.join(env.data_dir(), "raw")
    if not os.path.isdir(base):
        return 0
    n = 0
    for src in os.listdir(base):
        d = os.path.join(base, src)
        if not os.path.isdir(d):
            continue
        if node and src != node:
            continue
        n += len([f for f in os.listdir(d) if f.endswith(".json")])
    return n


def test_node_identity(db):
    nid = p2p.register_node()
    assert nid.startswith("node-")
    assert p2p.NODE_ID == nid
    c = connect()
    row = c.execute("select * from nodes_v2 where node_id=?", (nid,)).fetchone()
    c.close()
    assert row["protocol_version"] == p2p.PROTOCOL_VERSION
    assert "raw_sync" in json.loads(row["capabilities"])


def test_export_bundle(db):
    _seed_raw_files(3)
    b = p2p.export_bundle("raw", cursor=0, limit=10)
    assert b["node_id"] == p2p.NODE_ID
    assert b["protocol_version"] == p2p.PROTOCOL_VERSION
    assert len(b["items"]) == 3
    assert all("_hash" in it for it in b["items"])
    assert all(it["source"] == "node-a" for it in b["items"])


def test_sync_raw_dedup(db):
    """规则 27: 跨节点正常同步 + 重复同步去重。"""
    _seed_raw_files(3, node="node-a")
    b = _bundle([_raw_file("node-b", i) for i in range(3)])
    r1 = p2p.sync_from(b, "raw")
    assert r1["status"] == "OK" and r1["written"] == 3
    assert _local_raw_count("node-b") == 3
    # 重复同步 -> 去重, 不重复写入(规则 27)
    r2 = p2p.sync_from(b, "raw")
    assert r2["written"] == 0
    assert _local_raw_count("node-b") == 3


def test_sync_rejects_tampered_hash(db):
    _seed_raw_files(1)
    b = p2p.export_bundle("raw", cursor=0, limit=10)
    b["items"][0]["content"] = "tampered"  # 篡改但不更新 hash
    r = p2p.sync_from(b, "raw")
    assert r["rejected"] == 1
    assert r["status"] != "OK"


def test_sync_protocol_mismatch(db):
    _seed_raw_files(1)
    b = p2p.export_bundle("raw", cursor=0, limit=10)
    b["protocol_version"] = "9.9"
    r = p2p.sync_from(b, "raw")
    assert r["status"] == "PROTOCOL_MISMATCH"
    assert r["written"] == 0


def test_sync_conflict_no_overwrite(db):
    """规则 30/31: RAW 冲突 -> 两份都保留, 不覆盖。"""
    it = _raw_file("node-b", 0)
    b = _bundle([it], node="node-b")
    r1 = p2p.sync_from(b, "raw")
    assert r1["written"] == 1
    # 同 hash 名不同内容(内容被篡改但 data_hash 相同) -> conflict,
    # 原文件保留, 新内容落盘为 .<node>.json(规则 30: 两份并存)
    it2 = dict(it, content="different content")
    it2["_hash"] = data_hash({k: v for k, v in it2.items()
                              if k != "_hash"})
    b2 = _bundle([it2], node="node-b")
    r2 = p2p.sync_from(b2, "raw")
    d = env.raw_dir("node-b")
    files = [f for f in os.listdir(d) if f.endswith(".json")]
    assert r2["conflict"] >= 1
    assert len(files) == 2  # 两份并存


def test_incremental_sync_cursor(db):
    """规则 28/57: 增量补同步(断线恢复), 只拉取缺失范围。"""
    start = int(time.time() * 1000)
    _seed_raw_files(2, node="peer-a", start=start)
    b1 = p2p.export_bundle("raw", cursor=0, limit=10)
    assert len(b1["items"]) == 2
    r1 = p2p.sync_from(b1, "raw")
    # 本地已存在同源同内容 -> 幂等去重(规则 27)
    assert r1["written"] == 0

    # peer 侧新增 1 条(更大 mtime) -> 增量导出只含缺失范围
    _seed_raw_files(1, node="peer-a", start=start + 60000)
    b2 = p2p.export_bundle("raw", cursor=b1["to_cursor"], limit=10)
    assert b2["from_cursor"] == b1["to_cursor"]
    assert len(b2["items"]) == 1
    r2 = p2p.sync_from(b2, "raw")
    assert r2["written"] == 0  # 同源同内容去重
    assert _local_raw_count("peer-a") == 3


def test_sync_unified_conflict(db):
    """规则 31: Unified 相同去重, 冲突不覆盖。"""
    now = int(time.time() * 1000)
    row = {
        "canonical_match_id": "cm1", "source": "bb", "bookmaker": "BB",
        "source_match_id": "m1", "source_market_id": "mk1",
        "market_type": "asian_handicap", "period": "full_time",
        "line_raw": "-0.5", "line": -0.5, "side": "HOME",
        "option": "主队", "odds": 1.9, "event_time": now, "server_time": now,
        "received_at": now, "raw_ref": "r1", "pipeline_version": "0.2.0",
    }
    bundle = {
        "node_id": "node-b", "protocol_version": p2p.PROTOCOL_VERSION,
        "object_type": "unified", "from_cursor": 0, "to_cursor": 0,
        "items": [dict(row, _hash=data_hash(row))],
    }
    r1 = p2p.sync_from(bundle, "unified")
    assert r1["written"] == 1
    # 同 key 同值 -> 去重
    r2 = p2p.sync_from(bundle, "unified")
    assert r2["written"] == 0
    # 同 key 不同值 -> conflict(不覆盖)
    bundle2 = {
        "node_id": "node-b", "protocol_version": p2p.PROTOCOL_VERSION,
        "object_type": "unified", "from_cursor": 0, "to_cursor": 0,
        "items": [dict(row, odds=2.3, _hash=data_hash(dict(row, odds=2.3)))],
    }
    r3 = p2p.sync_from(bundle2, "unified")
    assert r3["conflict"] == 1
