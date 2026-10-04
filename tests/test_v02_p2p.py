"""V0.2 测试矩阵 4: P2P(规则 69)。

覆盖: Node Identity、正常同步、去重、hash 完整性、冲突(不覆盖)、
非法数据 REJECT、协议版本不匹配、增量补同步。
"""
import json
import time

import pytest

from p2p import node as p2p
from database.db import connect, data_hash, init as db_init


def _make_peer_bundle(rows, node="node-b", obj="raw"):
    """从任意 rows 构造 peer 数据包(模拟跨节点导出, 规则 30: RAW 保留采集节点身份)。"""
    items = []
    for r in rows:
        it = dict(r)
        it.pop("id", None)
        it["node_id"] = node  # RAW 归属采集节点(规则 30: 不同节点 RAW 并存)
        it["_hash"] = data_hash({k: v for k, v in it.items()
                                 if k != "_hash"})
        items.append(it)
    return {"node_id": node, "protocol_version": p2p.PROTOCOL_VERSION,
            "object_type": obj, "from_cursor": 0, "to_cursor": len(items),
            "items": items, "status": "OK"}


def _seed_raw(conn, n=3, node="node-a", base_t=None):
    now = base_t or int(time.time() * 1000)
    for i in range(n):
        conn.execute("""insert or ignore into matches(
            match_id,league_id,league,begin_time,home,away,source,status,updated_at)
            values(?,?,?,?,?,?,?,?,?)""",
            ("m%d" % i, 1, "L", now, "A", "B", node, "pre", now))
        conn.execute("""insert or ignore into markets(
            market_id,match_id,mty,pe,updated_at)
            values(?,?,?,?,?)""",
            ("mk%d" % i, "m%d" % i, "3", "0", now))
        conn.execute("""insert or ignore into snapshots(
            match_id,market_id,option_index,option,line,odds,
            collected_at,node_id,data_hash)
            values(?,?,?,?,?,?,?,?,?)""",
            ("m%d" % i, "mk%d" % i, 0, "opt%d" % i, "-0.5", 1.9,
             now + i * 1000, node, data_hash({"x": i, "t": now})))
    conn.commit()


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
    _seed_raw(db, 3)
    b = p2p.export_bundle("raw", cursor=0, limit=10)
    assert b["node_id"] == p2p.NODE_ID
    assert b["protocol_version"] == p2p.PROTOCOL_VERSION
    assert len(b["items"]) == 3
    assert all("_hash" in it for it in b["items"])


def test_sync_raw_dedup(db):
    """规则 27: 跨节点正常同步 + 重复同步去重。"""
    _seed_raw(db, 3, node="node-a")
    c = connect()
    rows = c.execute("select * from snapshots order by id").fetchall()
    c.close()
    b = _make_peer_bundle(rows, node="node-b")
    r1 = p2p.sync_from(b, "raw")
    assert r1["status"] == "OK" and r1["written"] == 3
    # 重复同步 -> 去重, 不重复写入(规则 27)
    r2 = p2p.sync_from(b, "raw")
    assert r2["written"] == 0


def test_sync_rejects_tampered_hash(db):
    _seed_raw(db, 1)
    b = p2p.export_bundle("raw", cursor=0, limit=10)
    b["items"][0]["odds"] = 99.9  # 篡改但不更新 hash
    r = p2p.sync_from(b, "raw")
    assert r["rejected"] == 1
    assert r["status"] != "OK"


def test_sync_protocol_mismatch(db):
    _seed_raw(db, 1)
    b = p2p.export_bundle("raw", cursor=0, limit=10)
    b["protocol_version"] = "9.9"
    r = p2p.sync_from(b, "raw")
    assert r["status"] == "PROTOCOL_MISMATCH"
    assert r["written"] == 0


def test_sync_conflict_no_overwrite(db):
    """规则 30/31: RAW 冲突 -> 两份都保留, 不覆盖。"""
    c = connect()
    _seed_raw(c, 1)
    c.close()
    b = p2p.export_bundle("raw", cursor=0, limit=10)
    # 本地已有同 node 同记录, 但值不同(改 hash 后仍冲突因 key 相同)
    b["items"][0]["odds"] = 2.5
    b["items"][0]["_hash"] = data_hash(
        {k: v for k, v in b["items"][0].items() if k != "_hash"})
    r = p2p.sync_from(b, "raw", force=False)
    c = connect()
    n = c.execute(
        "select count(*) from snapshots where match_id='m0'").fetchone()[0]
    c.close()
    assert n == 1  # 原记录保留


def test_incremental_sync_cursor(db):
    """规则 28/57: 增量补同步(断线恢复), 只拉取缺失范围。"""
    # peer 侧有 2 条
    _seed_raw(db, 2, node="node-a")
    c = connect()
    rows1 = c.execute("select * from snapshots where id<=2 order by id").fetchall()
    c.close()
    b1 = _make_peer_bundle(rows1, node="node-b")
    r1 = p2p.sync_from(b1, "raw")
    assert r1["written"] == 2

    # peer 侧新增 1 条(更大 id)
    _seed_raw(db, 1, node="node-a", base_t=int(time.time() * 1000))
    c = connect()
    rows2 = c.execute("select * from snapshots where id>2 order by id").fetchall()
    c.close()
    b2 = _make_peer_bundle(rows2, node="node-b")
    r2 = p2p.sync_from(b2, "raw")
    assert r2["written"] == 1


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
