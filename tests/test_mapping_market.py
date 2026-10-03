"""Unit Test: Market Mapping 显式状态机 + 盘口标准化(规则 7/7.1/7.2/7.3/7.4)。

覆盖: MAPPED / UNMAPPED / INVALID, asian_handicap / total / 1x2 标准化,
SX 源类型映射, side 队名前缀检测。
"""
import pytest

from mapping.market import normalize, MTY
from mapping.market_service import map_and_save
from sources.base import NormalizedRecord


def rec(**kw):
    base = dict(
        source="bb",
        bookmaker="BB",
        source_match_id="m1",
        canonical_match_id=None,
        source_market_id="mm1",
        market_type="1000",
        period="0",
        line_raw="-0.5",
        line=None,
        option="主队-0.5",
        odds=1.90,
        home="Manchester United",
        away="Chelsea",
        event_time=1000,
        server_time=1000,
        received_at=1000,
        raw_ref="raw-1",
    )
    base.update(kw)
    return NormalizedRecord(**base)


def test_market_ah_mapped():
    m = normalize(rec())
    assert m.status == "MAPPED"
    assert m.market_type == "asian_handicap"
    assert m.line == -0.5
    assert m.side == "HOME"

def test_market_total():
    m = normalize(rec(market_type="1007", option="大", line_raw="2.5"))
    assert m.status == "MAPPED"
    assert m.market_type == "over_under"
    assert m.line == 2.5
    assert m.side == "OVER"


def test_market_1x2():
    m = normalize(rec(market_type="1005", option="主胜", line_raw=None))
    assert m.status == "MAPPED"
    assert m.market_type == "1x2"
    assert m.side == "HOME"


def test_market_unknown_type_unmapped():
    m = normalize(rec(market_type="9999"))
    assert m.status == "UNMAPPED"


def test_market_missing_odds_invalid():
    m = normalize(rec(odds=None))
    assert m.status == "INVALID"


def test_market_line_required_invalid():
    m = normalize(rec(market_type="1000", line_raw=""))
    assert m.status == "INVALID"


def test_market_sx_type_mapping():
    """SX 源数字类型由 market.py 统一映射(规则 7)。"""
    assert MTY["3"] == "asian_handicap"
    assert MTY["2"] == "total"
    assert MTY["52"] == "1x2"
    assert MTY["1"] == "binary"


def test_sx_ah_side_detect():
    """SX 队名前缀: 'Internacional de Bogota -1.5' => HOME。"""
    m = normalize(rec(
        source="sx", bookmaker="SX", market_type="3",
        line_raw="-1.5", line=None,
        home="Internacional de Bogota", away="Real Cartagena",
        option="Internacional de Bogota -1.5", odds=1.83,
    ))
    assert m.status == "MAPPED"
    assert m.side == "HOME"
    assert m.line == -1.5


def test_sx_total_detect():
    m = normalize(rec(
        source="sx", bookmaker="SX", market_type="2",
        line_raw="2.5", option="Over 2.5", odds=1.87,
    ))
    assert m.status == "MAPPED"
    assert m.market_type == "total"
    assert m.line == 2.5
    assert m.side == "OVER"


def test_map_and_save_persists(db):
    r = rec()
    m = map_and_save(r, canonical_match_id="cm_1")
    assert m.status == "MAPPED"
    row = db.execute(
        "select * from market_mappings where source_market_id='mm1'").fetchone()
    assert row is not None
    assert row["status"] == "MAPPED"
    assert row["canonical_match_id"] == "cm_1"


def test_map_and_save_invalid_persisted(db):
    r = rec(odds=None)
    m = map_and_save(r, canonical_match_id="cm_1")
    assert m.status == "INVALID"
    row = db.execute(
        "select * from market_mappings where source_market_id='mm1'").fetchone()
    assert row is not None
    assert row["status"] == "INVALID"
