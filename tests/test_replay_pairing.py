import unittest
import os
import sys
import sqlite3
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import replay.event_v1 as R1
import replay.event_v2 as R2


class TestReplayPairing(unittest.TestCase):
    def setUp(self):
        self.tmpdb = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.tmpdb.close()
        R1.DB = self.tmpdb.name
        R2.DB = self.tmpdb.name

        c = sqlite3.connect(self.tmpdb.name)
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
        c.execute("""create table if not exists replay_events_v1(
         id integer primary key,old_time integer,new_time integer,
         event_count integer,created_at integer,
         replay_hash text unique)""")
        c.execute("""create table if not exists replay_events_v2(
         id integer primary key,old_time integer,new_time integer,
         canonical_match_id text,source text,market_type text,period text,
         side text,option text,old_line_raw text,new_line_raw text,
         old_odds real,new_odds real,odds_direction text,
         line_direction text,line_change_type text,event_type text,
         event_hash text unique,created_at integer)""")
        c.close()

    def tearDown(self):
        try:
            os.unlink(self.tmpdb.name)
        except Exception:
            pass

    def _base_row(self, **kw):
        base = {
            "canonical_match_id": "cm_123",
            "source": "BB",
            "bookmaker": "",
            "source_match_id": "match_1",
            "source_market_id": "mkt_1",
            "market_type": "HDP",
            "period": "FULL",
            "line_raw": "-0.5",
            "line": -0.5,
            "side": "HOME",
            "option": "HOME",
            "odds": 1.90,
            "event_time": 1700000000,
            "server_time": 1700000000,
            "received_at": 1000,
            "raw_ref": "",
            "created_at": 1000,
        }
        base.update(kw)
        return base

    def insert_rows(self, rows):
        c = sqlite3.connect(self.tmpdb.name)
        cur = c.cursor()
        for r in rows:
            cur.execute("""insert into unified_snapshots(canonical_match_id,source,bookmaker,source_match_id,source_market_id,market_type,period,line_raw,line,side,option,odds,event_time,server_time,received_at,raw_ref,created_at)
                           values(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                        (r["canonical_match_id"], r["source"], r["bookmaker"], r["source_match_id"], r["source_market_id"],
                         r["market_type"], r["period"], r["line_raw"], r["line"], r["side"], r["option"], r["odds"],
                         r["event_time"], r["server_time"], r["received_at"], r["raw_ref"], r["created_at"]))
        c.commit()
        c.close()

    def test_v1_same_valid_market_pairs(self):
        rows_a = [self._base_row(received_at=2000000000000)]
        rows_b = [self._base_row(received_at=2000000001000, line_raw="-0.75", line=-0.75, odds=1.81)]
        self.insert_rows(rows_a + rows_b)
        c = sqlite3.connect(self.tmpdb.name)
        c.row_factory = sqlite3.Row
        n = R1.replay(c, 2000000000000, 2000000001000)
        c.close()
        self.assertTrue(n >= 1)

    def test_v1_different_market_not_paired(self):
        rows_a = [self._base_row(received_at=2000000000000, source_market_id="mkt_1")]
        rows_b = [self._base_row(received_at=2000000001000, source_market_id="mkt_2", line_raw="-0.75", line=-0.75, odds=1.81)]
        self.insert_rows(rows_a + rows_b)
        c = sqlite3.connect(self.tmpdb.name)
        c.row_factory = sqlite3.Row
        n = R1.replay(c, 2000000000000, 2000000001000)
        c.close()
        self.assertEqual(n, 0)

    def test_v1_invalid_market_not_paired(self):
        rows_a = [self._base_row(received_at=2000000000000, source_market_id="")]
        rows_b = [self._base_row(received_at=2000000001000, source_market_id="", line_raw="-0.75", line=-0.75, odds=1.81)]
        self.insert_rows(rows_a + rows_b)
        c = sqlite3.connect(self.tmpdb.name)
        c.row_factory = sqlite3.Row
        n = R1.replay(c, 2000000000000, 2000000001000)
        c.close()
        self.assertEqual(n, 0)

    def test_v1_different_match_not_cross_paired(self):
        rows_a = [self._base_row(received_at=2000000000000, canonical_match_id="cm1")]
        rows_b = [self._base_row(received_at=2000000001000, canonical_match_id="cm2", line_raw="-0.75", line=-0.75, odds=1.81)]
        self.insert_rows(rows_a + rows_b)
        c = sqlite3.connect(self.tmpdb.name)
        c.row_factory = sqlite3.Row
        n = R1.replay(c, 2000000000000, 2000000001000)
        c.close()
        self.assertEqual(n, 0)

    def test_v1_no_match_no_error(self):
        rows_a = [self._base_row(received_at=2000000000000)]
        self.insert_rows(rows_a)
        c = sqlite3.connect(self.tmpdb.name)
        c.row_factory = sqlite3.Row
        n = R1.replay(c, 2000000000000, 2000000001000)
        c.close()
        self.assertEqual(n, 0)

    def test_v2_same_valid_market_pairs(self):
        rows_a = [self._base_row(received_at=2000000000000)]
        rows_b = [self._base_row(received_at=2000000001000, line_raw="-0.75", line=-0.75, odds=1.81)]
        self.insert_rows(rows_a + rows_b)
        R2.main()
        c = sqlite3.connect(self.tmpdb.name)
        c.row_factory = sqlite3.Row
        cnt = c.execute("select count(*) as n from replay_events_v2").fetchone()["n"]
        c.close()
        self.assertTrue(cnt >= 1)

    def test_v2_different_market_not_paired(self):
        rows_a = [self._base_row(received_at=2000000000000, source_market_id="mkt_1")]
        rows_b = [self._base_row(received_at=2000000001000, source_market_id="mkt_2", line_raw="-0.75", line=-0.75, odds=1.81)]
        self.insert_rows(rows_a + rows_b)
        R2.main()
        c = sqlite3.connect(self.tmpdb.name)
        c.row_factory = sqlite3.Row
        cnt = c.execute("select count(*) as n from replay_events_v2").fetchone()["n"]
        c.close()
        self.assertEqual(cnt, 0)

    def test_v2_invalid_market_not_paired(self):
        rows_a = [self._base_row(received_at=2000000000000, source_market_id="None")]
        rows_b = [self._base_row(received_at=2000000001000, source_market_id="", line_raw="-0.75", line=-0.75, odds=1.81)]
        self.insert_rows(rows_a + rows_b)
        R2.main()
        c = sqlite3.connect(self.tmpdb.name)
        c.row_factory = sqlite3.Row
        cnt = c.execute("select count(*) as n from replay_events_v2").fetchone()["n"]
        c.close()
        self.assertEqual(cnt, 0)

    def test_v2_different_match_not_cross_paired(self):
        rows_a = [self._base_row(received_at=2000000000000, canonical_match_id="cm1")]
        rows_b = [self._base_row(received_at=2000000001000, canonical_match_id="cm2", line_raw="-0.75", line=-0.75, odds=1.81)]
        self.insert_rows(rows_a + rows_b)
        R2.main()
        c = sqlite3.connect(self.tmpdb.name)
        c.row_factory = sqlite3.Row
        cnt = c.execute("select count(*) as n from replay_events_v2").fetchone()["n"]
        c.close()
        self.assertEqual(cnt, 0)

    def test_v2_no_match_no_error(self):
        rows_a = [self._base_row(received_at=2000000000000)]
        self.insert_rows(rows_a)
        R2.main()
        c = sqlite3.connect(self.tmpdb.name)
        c.row_factory = sqlite3.Row
        cnt = c.execute("select count(*) as n from replay_events_v2").fetchone()["n"]
        c.close()
        self.assertEqual(cnt, 0)


if __name__ == "__main__":
    unittest.main()
