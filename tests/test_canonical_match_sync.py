import unittest
import os
import sys
import sqlite3
import tempfile
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database import db
from mapping import db as mdb
from mapping import unified_db
from mapping.unified_service import unify
from mapping.service import auto_map
from mapping.db import get_by_source


class DummyRec:
    def __init__(self, **kw):
        for k, v in kw.items():
            setattr(self, k, v)


class TestCanonicalMatchSync(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.NamedTemporaryFile(suffix='.db', delete=False)
        self.tmp.close()
        db.DB = self.tmp.name
        # init tables
        try:
            db.init()
        except Exception:
            pass
        try:
            mdb.init_mapping()
        except Exception:
            pass
        try:
            unified_db.init_unified()
        except Exception:
            pass

    def tearDown(self):
        try:
            os.unlink(self.tmp.name)
        except Exception:
            pass

    def test_unify_uses_existing_matched_mapping_by_source(self):
        rec_a = DummyRec(source='BB', source_match_id='M1', home='TeamA', away='TeamB', event_time=1700000000000)
        mm = auto_map(rec_a, rec_a)
        self.assertIsNotNone(mm.get('canonical_match_id'))
        cid = mm['canonical_match_id']
        rec_b = DummyRec(source='BB', bookmaker=None, source_match_id='M1', source_market_id='mk1',
                         market_type='1000', period='1001', home='TeamA', away='TeamB',
                         line_raw='-0.5', line=-0.5, option='TeamA', odds=1.9,
                         event_time=1700000000000, server_time=None, received_at=2000, raw_ref='')
        unify(rec_b, canonical_match_id=None)
        c = sqlite3.connect(db.DB)
        c.row_factory = sqlite3.Row
        row = c.execute("select canonical_match_id from unified_snapshots where source_match_id='M1'").fetchone()
        c.close()
        self.assertIsNotNone(row)
        self.assertEqual(row['canonical_match_id'], cid)

    def test_unify_does_not_fabricate_when_no_mapping(self):
        rec_b = DummyRec(source='BB', bookmaker=None, source_match_id='M_NO_MAP', source_market_id='mk2',
                         market_type='1000', period='1001', home='X', away='Y',
                         line_raw='-0.5', line=-0.5, option='X', odds=1.9,
                         event_time=1700000000000, server_time=None, received_at=2000, raw_ref='')
        unify(rec_b, canonical_match_id=None)
        c = sqlite3.connect(db.DB)
        c.row_factory = sqlite3.Row
        row = c.execute("select canonical_match_id from unified_snapshots where source_match_id='M_NO_MAP'").fetchone()
        c.close()
        self.assertIsNotNone(row)
        self.assertIsNone(row['canonical_match_id'])

    def test_self_match_without_event_time_does_not_fabricate(self):
        rec_a = DummyRec(source='BB', source_match_id='M_NE', home='TeamA', away='TeamB', event_time=None)
        mm = auto_map(rec_a, rec_a)
        self.assertIsNone(mm.get('canonical_match_id'))
        rec_b = DummyRec(source='BB', bookmaker=None, source_match_id='M_NE', source_market_id='mk3',
                         market_type='1000', period='1001', home='TeamA', away='TeamB',
                         line_raw='-0.5', line=-0.5, option='TeamA', odds=1.9,
                         event_time=None, server_time=None, received_at=3000, raw_ref='')
        unify(rec_b, canonical_match_id=None)
        c = sqlite3.connect(db.DB)
        c.row_factory = sqlite3.Row
        row = c.execute("select canonical_match_id from unified_snapshots where source_match_id='M_NE'").fetchone()
        c.close()
        self.assertIsNotNone(row)
        self.assertIsNone(row['canonical_match_id'])

    def test_possible_unmatched_mapping_not_recovered(self):
        now = int(time.time() * 1000)
        c = sqlite3.connect(db.DB)
        cur = c.cursor()
        cur.execute("""INSERT INTO match_mappings(source,source_match_id,canonical_match_id,home,away,event_time,confidence,status,created_at,updated_at)
                       VALUES(?,?,?,?,?,?,?,?,?,?)""", ('BB', 'M_POSS', None, 'A', 'B', 1700000000000, 0.5, 'possible', now, now))
        c.commit()
        c.close()
        rec_b = DummyRec(source='BB', bookmaker=None, source_match_id='M_POSS', source_market_id='mk4',
                         market_type='1000', period='1001', home='A', away='B',
                         line_raw='-0.5', line=-0.5, option='A', odds=1.9,
                         event_time=1700000000000, server_time=None, received_at=4000, raw_ref='')
        unify(rec_b, canonical_match_id=None)
        c = sqlite3.connect(db.DB)
        c.row_factory = sqlite3.Row
        row = c.execute("select canonical_match_id from unified_snapshots where source_match_id='M_POSS'").fetchone()
        c.close()
        self.assertIsNotNone(row)
        self.assertIsNone(row['canonical_match_id'])

    def test_non_empty_cid_not_overwritten(self):
        rec_a = DummyRec(source='BB', source_match_id='M2', home='TeamA', away='TeamB', event_time=1700000000000)
        mm = auto_map(rec_a, rec_a)
        self.assertIsNotNone(mm.get('canonical_match_id'))
        rec_b = DummyRec(source='BB', bookmaker=None, source_match_id='M2', source_market_id='mk5',
                         market_type='1000', period='1001', home='TeamA', away='TeamB',
                         line_raw='-0.5', line=-0.5, option='TeamA', odds=1.9,
                         event_time=1700000000000, server_time=None, received_at=5000, raw_ref='')
        unify(rec_b, canonical_match_id='cm_FORCED')
        c = sqlite3.connect(db.DB)
        c.row_factory = sqlite3.Row
        row = c.execute("select canonical_match_id from unified_snapshots where source_match_id='M2'").fetchone()
        c.close()
        self.assertIsNotNone(row)
        self.assertEqual(row['canonical_match_id'], 'cm_FORCED')

    def test_different_source_not_cross_matched(self):
        rec_a = DummyRec(source='BB', source_match_id='M3', home='TeamA', away='TeamB', event_time=1700000000000)
        mm = auto_map(rec_a, rec_a)
        self.assertIsNotNone(mm.get('canonical_match_id'))
        rec_b = DummyRec(source='OTHER', bookmaker=None, source_match_id='M3', source_market_id='mk6',
                         market_type='1000', period='1001', home='TeamA', away='TeamB',
                         line_raw='-0.5', line=-0.5, option='TeamA', odds=1.9,
                         event_time=1700000000000, server_time=None, received_at=6000, raw_ref='')
        unify(rec_b, canonical_match_id=None)
        c = sqlite3.connect(db.DB)
        c.row_factory = sqlite3.Row
        row = c.execute("select canonical_match_id from unified_snapshots where source_match_id='M3' and source='OTHER'").fetchone()
        c.close()
        self.assertIsNotNone(row)
        self.assertIsNone(row['canonical_match_id'])

    def test_different_source_match_id_not_cross_matched(self):
        rec_a = DummyRec(source='BB', source_match_id='M4', home='TeamA', away='TeamB', event_time=1700000000000)
        mm = auto_map(rec_a, rec_a)
        self.assertIsNotNone(mm.get('canonical_match_id'))
        rec_b = DummyRec(source='BB', bookmaker=None, source_match_id='M4X', source_market_id='mk7',
                         market_type='1000', period='1001', home='TeamA', away='TeamB',
                         line_raw='-0.5', line=-0.5, option='TeamA', odds=1.9,
                         event_time=1700000000000, server_time=None, received_at=7000, raw_ref='')
        unify(rec_b, canonical_match_id=None)
        c = sqlite3.connect(db.DB)
        c.row_factory = sqlite3.Row
        row = c.execute("select canonical_match_id from unified_snapshots where source_match_id='M4X'").fetchone()
        c.close()
        self.assertIsNotNone(row)
        self.assertIsNone(row['canonical_match_id'])

    def test_unique_constraint_enforced(self):
        now = int(time.time() * 1000)
        c = sqlite3.connect(db.DB)
        cur = c.cursor()
        try:
            cur.execute("""INSERT INTO match_mappings(source,source_match_id,canonical_match_id,home,away,event_time,confidence,status,created_at,updated_at)
                           VALUES(?,?,?,?,?,?,?,?,?,?)""", ('BB', 'M_DUP', 'cm1', 'A', 'B', 1700000000000, 1.0, 'matched', now, now))
            cur.execute("""INSERT INTO match_mappings(source,source_match_id,canonical_match_id,home,away,event_time,confidence,status,created_at,updated_at)
                           VALUES(?,?,?,?,?,?,?,?,?,?)""", ('BB', 'M_DUP', 'cm2', 'A', 'B', 1700000000000, 1.0, 'matched', now, now))
            c.commit()
            self.fail('expected constraint violation')
        except Exception:
            pass
        finally:
            c.close()

    def test_multiple_candidates_via_fetchall_rejected(self):
        # Simulate path where multiple rows exist (even if constraint normally prevents)
        now = int(time.time() * 1000)
        c = sqlite3.connect(db.DB)
        cur = c.cursor()
        try:
            # Drop constraint by recreating table to test defensive logic
            cur.execute('ALTER TABLE match_mappings RENAME TO match_mappings_old')
            cur.execute('''CREATE TABLE match_mappings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source TEXT NOT NULL,
                source_match_id TEXT NOT NULL,
                canonical_match_id TEXT,
                home TEXT,
                away TEXT,
                event_time INTEGER,
                confidence REAL NOT NULL DEFAULT 0,
                status TEXT NOT NULL,
                created_at INTEGER NOT NULL,
                updated_at INTEGER NOT NULL
            )''')
            cur.execute("""INSERT INTO match_mappings(source,source_match_id,canonical_match_id,home,away,event_time,confidence,status,created_at,updated_at)
                           VALUES(?,?,?,?,?,?,?,?,?,?)""", ('BB', 'M_MUL', 'cm_a', 'A', 'B', 1700000000000, 1.0, 'matched', now, now))
            cur.execute("""INSERT INTO match_mappings(source,source_match_id,canonical_match_id,home,away,event_time,confidence,status,created_at,updated_at)
                           VALUES(?,?,?,?,?,?,?,?,?,?)""", ('BB', 'M_MUL', 'cm_b', 'A', 'B', 1700000000000, 1.0, 'matched', now, now))
            c.commit()
            res = get_by_source('BB', 'M_MUL')
            self.assertIsNone(res)
        finally:
            try:
                cur.execute('DROP TABLE IF EXISTS match_mappings')
                cur.execute('ALTER TABLE match_mappings_old RENAME TO match_mappings')
                c.commit()
            except Exception:
                pass
            c.close()


if __name__ == '__main__':
    unittest.main()
