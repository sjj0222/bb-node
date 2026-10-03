"""Unit Test: Match Mapping 显式状态机(规则 6/33)。

覆盖: MAPPED / UNMAPPED / PENDING / INVALID
"""
import pytest

from mapping.match import map_match, name_score
from mapping.service import auto_map


class Rec:
    def __init__(self, source, smid, home, away, et, **kw):
        self.source = source
        self.source_match_id = smid
        self.home = home
        self.away = away
        self.event_time = et


def test_normalized_score():
    assert name_score("Manchester United", "Manchester United") == 1.0
    s = name_score("Manchester United", "Man Utd")
    assert s > 0.3


def test_match_mapped():
    a = Rec("bb", "1", "Manchester United", "Chelsea", 1000)
    r = map_match(a, a)
    assert r["status"] == "MAPPED"
    assert r["canonical_match_id"]
    assert r["confidence"] >= 0.88


def test_match_unmapped():
    a = Rec("bb", "1", "Manchester United", "Chelsea", 1000)
    b = Rec("sx", "x", "Real Madrid", "Barcelona", 1000)
    r = map_match(a, b)
    assert r["status"] == "UNMAPPED"
    assert r["canonical_match_id"] is None


def test_match_invalid_empty_teams():
    a = Rec("bb", "1", "", "", 1000)
    r = map_match(a, a)
    assert r["status"] == "INVALID"
    assert r["canonical_match_id"] is None


def test_match_pending_low_confidence():
    a = Rec("bb", "1", "Manchester United FC", "Chelsea", 1000)
    b = Rec("sx", "x", "Man United", "Chelsea London", 1000)
    r = map_match(a, b)
    # 不同比赛(客队不同)且队名不精确 => 不允许强行映射
    assert r["status"] in ("PENDING", "UNMAPPED")
    if r["status"] == "PENDING":
        assert r["canonical_match_id"] is None


def test_match_conflict_same_names_diff_time():
    """规则 6.3/33: 队名完全一致但时间差异明显 => CONFLICT(禁止强行猜测)。"""
    a = Rec("bb", "1", "Manchester United", "Chelsea", 1000)
    b = Rec("sx", "x", "Manchester United", "Chelsea", 1000 + 30 * 60 * 60 * 1000)
    r = map_match(a, b)
    assert r["status"] == "CONFLICT"
    assert r["canonical_match_id"] is None


def test_canonical_cross_source_same():
    """不同 Source 同一场比赛 => 相同 canonical_match_id(规则 6.1)。"""
    a = Rec("bb", "1", "Manchester United", "Chelsea", 1000)
    b = Rec("sx", "x", "Manchester United", "Chelsea", 1000)
    ra = map_match(a, a)
    rb = map_match(b, b)
    assert ra["canonical_match_id"] == rb["canonical_match_id"]


def test_canonical_different_matches():
    a = Rec("bb", "1", "Manchester United", "Chelsea", 1000)
    b = Rec("sx", "x", "Arsenal", "Tottenham", 2000)
    ra = map_match(a, a)
    rb = map_match(b, b)
    assert ra["canonical_match_id"] != rb["canonical_match_id"]


def test_auto_map_saves(db):
    a = Rec("bb", "1", "Manchester United", "Chelsea", 1000)
    d = auto_map(a, a)
    assert d["status"] == "MAPPED"
    row = db.execute("select * from match_mappings where source='bb' and source_match_id='1'").fetchone()
    assert row is not None
    assert row["status"] == "MAPPED"
    assert row["canonical_match_id"] == d["canonical_match_id"]
