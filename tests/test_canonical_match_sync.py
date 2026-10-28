import unittest
import os
import sys
import sqlite3
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database import db
from mapping import db as mdb
from mapping import unified_db
from mapping.unified_service import unify
from mapping.service import auto_map


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


if __name__ == '__main__':
    unittest.main()
