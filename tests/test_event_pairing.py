import unittest
import sys
import os
import sqlite3
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import events.engine_v3 as E


class TestEventPairing(unittest.TestCase):
    """事件配对键包含 source_market_id 的验证测试。

    核心缺陷：events/engine_v3.py 的配对键不包含 source_market_id，
    导致同一比赛内不同盘口档位（不同 market_id）的选项可能被错误配对。
    """

    def setUp(self):
        # 使用临时文件数据库，避免写入生产数据库
        self.tmpdb = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.tmpdb.close()
        E.DB = self.tmpdb.name

        # Monkeypatch start/finish 避免写入 ~/bb_node/data/bb.db
        self.orig_start = E.start
        self.orig_finish = E.finish
        E.start = lambda *args, **kwargs: None
        E.finish = lambda *args, **kwargs: None

        c = sqlite3.connect(E.DB)
        c.row_factory = sqlite3.Row
        c.execute("""create table if not exists unified_snapshots(
         id integer primary key AUTOINCREMENT,
         canonical_match_id text,
         source text NOT NULL,
         bookmaker text,
         source_match_id text NOT NULL,
         source_market_id text NOT NULL,
         market_type text NOT NULL,
         period text,
         line_raw text,
         line real,
         side text,
         option text NOT NULL,
         odds real,
         event_time integer,
         server_time integer,
         received_at integer NOT NULL,
         raw_ref text,
         created_at integer NOT NULL)""")
        c.execute("""create table if not exists events_v3(
         id integer primary key,
         canonical_match_id text,source text,
         source_match_id text,market_type text,period text,side text,
         option text,old_line_raw text,new_line_raw text,old_odds real,
         new_odds real,odds_direction text,line_direction text,
         line_change_type text,event_type text,old_time integer,new_time integer,
         event_hash text unique,created_at integer)""")
        c.commit()
        c.close()

    def tearDown(self):
        E.start = self.orig_start
        E.finish = self.orig_finish
        try:
            os.unlink(self.tmpdb.name)
        except OSError:
            pass

    def insert_rows(self, rows):
        c = sqlite3.connect(E.DB)
        c.row_factory = sqlite3.Row
        for r in rows:
            c.execute("""insert into unified_snapshots
            (canonical_match_id,source,source_match_id,source_market_id,
             market_type,period,side,option,line_raw,line,odds,
             received_at,created_at)
            values(?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (r["canonical_match_id"], r["source"], r["source_match_id"],
             r["source_market_id"], r["market_type"], r["period"],
             r["side"], r["option"], r["line_raw"], r["line"],
             r["odds"], r["received_at"], r["created_at"]))
        c.commit()
        c.close()

    def count_events(self, event_type=None):
        c = sqlite3.connect(E.DB)
        c.row_factory = sqlite3.Row
        if event_type:
            count = c.execute(
                "select count(*) from events_v3 where event_type=?",
                (event_type,)
            ).fetchone()[0]
        else:
            count = c.execute("select count(*) from events_v3").fetchone()[0]
        c.close()
        return count

    def _base_row(self, overrides=None):
        row = {
            "canonical_match_id": "cm_123",
            "source": "bb",
            "source_match_id": "match_1",
            "source_market_id": "mkt_1",
            "market_type": "1000",
            "period": "1001",
            "side": "home",
            "option": "热那亚",
            "line_raw": "-0.5",
            "line": -0.5,
            "odds": 1.83,
            "received_at": 1000,
            "created_at": 1000,
        }
        if overrides:
            row.update(overrides)
        return row

    def test_same_market_id_pairs_correctly(self):
        """同一 source_market_id 的选项应该正确配对并产生 LINE_CHANGE 事件。"""
        rows_a = [self._base_row()]
        rows_b = [
            self._base_row({
                "received_at": 2000,
                "created_at": 2000,
                "line_raw": "-0.5/1",
                "line": -0.75,
                "odds": 1.81,
            }),
        ]
        self.insert_rows(rows_a + rows_b)
        E.main()
        # 赔率变化 → WATER_CHANGE，盘口变化 → LINE_CHANGE，共 2 个事件
        self.assertEqual(self.count_events(), 2)
        self.assertEqual(self.count_events("LINE_CHANGE"), 1)
        self.assertEqual(self.count_events("WATER_CHANGE"), 1)

    def test_different_market_id_not_paired(self):
        """不同 source_market_id 不应该被错误配对。

        场景：同一比赛内两个不同盘口档位（mkt_1 line=-0.5, mkt_2 line=-0.74），
        B 侧 mkt_1 盘口调整到 -0.75。不带 source_market_id 的配对键会把
        mkt_2（diff=0.01）误判为更接近的候选，导致跨市场错配。
        带 source_market_id 后，mkt_1 只与 mkt_1 配对，mkt_2 不与 B 行配对。
        """
        rows_a = [
            self._base_row({
                "source_market_id": "mkt_1",
                "line_raw": "-0.5",
                "line": -0.5,
                "odds": 1.83,
            }),
            self._base_row({
                "source_market_id": "mkt_2",
                "line_raw": "-0.75",
                "line": -0.74,
                "odds": 1.90,
            }),
        ]
        rows_b = [
            self._base_row({
                "source_market_id": "mkt_1",
                "received_at": 2000,
                "created_at": 2000,
                "line_raw": "-0.75",
                "line": -0.75,
                "odds": 1.81,
            }),
        ]
        self.insert_rows(rows_a + rows_b)
        E.main()
        # 只有 mkt_1 应该配对（1 个 LINE_CHANGE + 1 WATER_CHANGE）
        # mkt_2 没有匹配的 B 行，不应产生事件
        self.assertEqual(self.count_events(), 2)
        self.assertEqual(self.count_events("LINE_CHANGE"), 1)
        self.assertEqual(self.count_events("WATER_CHANGE"), 1)

    def test_different_match_not_paired(self):
        """不同 canonical_match_id 不应该配对。"""
        rows_a = [self._base_row()]
        rows_b = [
            self._base_row({
                "canonical_match_id": "cm_456",
                "source_match_id": "match_2",
                "received_at": 2000,
                "created_at": 2000,
            }),
        ]
        self.insert_rows(rows_a + rows_b)
        E.main()
        self.assertEqual(self.count_events(), 0)

    def test_empty_source_market_id_pairs_with_empty(self):
        """source_market_id 为空字符串的行，无效ID不参与配对。"""
        rows_a = [
            self._base_row({"source_market_id": ""}),
        ]
        rows_b = [
            self._base_row({
                "source_market_id": "",
                "received_at": 2000,
                "created_at": 2000,
                "line_raw": "-0.75",
                "line": -0.75,
                "odds": 1.81,
            }),
        ]
        self.insert_rows(rows_a + rows_b)
        E.main()
        self.assertEqual(self.count_events(), 0)

    def test_no_backfill_for_unmatched_b_rows(self):
        """B 侧没有匹配的 A 行时，不应静默产生事件。"""
        rows_a = [
            self._base_row({"source_market_id": "mkt_1"}),
        ]
        rows_b = [
            self._base_row({
                "source_market_id": "mkt_2",
                "received_at": 2000,
                "created_at": 2000,
                "line_raw": "-0.5",
                "line": -0.5,
                "odds": 1.81,
            }),
        ]
        self.insert_rows(rows_a + rows_b)
        E.main()
        self.assertEqual(self.count_events(), 0)

    def test_string_none_source_market_id_not_paired(self):
        """字符串 \"None\" 为无效ID，不参与配对。"""
        rows_a = [
            self._base_row({"source_market_id": "None"}),
        ]
        rows_b = [
            self._base_row({
                "source_market_id": "None",
                "received_at": 2000,
                "created_at": 2000,
                "line_raw": "-0.75",
                "line": -0.75,
                "odds": 1.81,
            }),
        ]
        self.insert_rows(rows_a + rows_b)
        E.main()
        self.assertEqual(self.count_events(), 0)

    def test_missing_source_market_id_not_paired(self):
        """缺失 source_market_id 字段应视为无效，不参与配对。"""
        c = sqlite3.connect(E.DB)
        cur = c.cursor()
        cur.execute("DROP TABLE IF EXISTS unified_snapshots")
        cur.execute("""create table if not exists unified_snapshots(
         id integer primary key AUTOINCREMENT,
         canonical_match_id text,
         source text NOT NULL,
         bookmaker text,
         source_match_id text NOT NULL,
         market_type text NOT NULL,
         period text,
         line_raw text,
         line real,
         side text,
         option text NOT NULL,
         odds real,
         event_time integer,
         server_time integer,
         received_at integer NOT NULL,
         raw_ref text,
         created_at integer NOT NULL)""")
        cur.execute("""insert into unified_snapshots(canonical_match_id,source,bookmaker,source_match_id,market_type,period,line_raw,line,side,option,odds,event_time,server_time,received_at,raw_ref,created_at)
                       values(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    ("cm_123","BB","","match_1","HDP","FULL","-0.5",-0.5,"HOME","HOME",1.90,1700000000,1700000000,1000,"","1000"))
        cur.execute("""insert into unified_snapshots(canonical_match_id,source,bookmaker,source_match_id,market_type,period,line_raw,line,side,option,odds,event_time,server_time,received_at,raw_ref,created_at)
                       values(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    ("cm_123","BB","","match_1","HDP","FULL","-0.75",-0.75,"HOME","HOME",1.81,1700000000,1700000000,2000,"","2000"))
        c.commit()
        c.close()
        E.main()
        self.assertEqual(self.count_events(), 0)
        # restore
        c = sqlite3.connect(E.DB)
        cur = c.cursor()
        cur.execute("DROP TABLE IF EXISTS unified_snapshots")
        cur.execute("""create table if not exists unified_snapshots(
         id integer primary key AUTOINCREMENT,
         canonical_match_id text,
         source text NOT NULL,
         bookmaker text,
         source_match_id text NOT NULL,
         source_market_id text NOT NULL,
         market_type text NOT NULL,
         period text,
         line_raw text,
         line real,
         side text,
         option text NOT NULL,
         odds real,
         event_time integer,
         server_time integer,
         received_at integer NOT NULL,
         raw_ref text,
         created_at integer NOT NULL)""")
        c.commit()
        c.close()


if __name__ == "__main__":
    unittest.main()
