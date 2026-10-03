"""Unit Test: Source Adapter(Normalized 层, 规则 5/3.3)与工具函数。

覆盖: BB normalize 字段, SX normalize, SX percentageOdds 基准,
BB 空 leagues = 全量采集(回归 bug)。
"""
import pytest

from sources.bb import BBAdapter, TARGET_LEAGUES
from sources.sx import SXBetAdapter, pct_to_decimal


def make_bb_match():
    """BB 真实 JSON 结构: 队名在 ts[], 盘口组 mg[].mks[].op[]。"""
    return {
        "id": "1001",
        "lg": {"id": 11020, "na": "欧洲国家联赛 A组"},
        "ts": [{"id": "1", "na": "Manchester United"},
               {"id": "2", "na": "Chelsea"}],
        "st": 1,
        "bt": 1791000000,
        "mg": [
            {"id": "5001", "mty": "1000", "pe": "0",
             "mks": [
                 {"id": "5002", "li": "-0.5",
                  "op": [
                      {"id": "9001", "na": "主队-0.5", "od": "1.90", "st": 1},
                      {"id": "9002", "na": "客队+0.5", "od": "1.95", "st": 1},
                  ]},
             ]},
        ],
    }


def test_bb_normalize_fields():
    a = BBAdapter()
    recs = a.normalize(make_bb_match(), 1234, raw_ref="test-raw")
    assert len(recs) == 2
    r = recs[0]
    assert r.source == "bb"
    assert r.source_match_id == "1001"
    assert r.home == "Manchester United"
    assert r.away == "Chelsea"
    assert r.market_type == "1000"  # 源格式, 由 market.py 映射
    assert r.odds == 1.90
    assert r.received_at == 1234
    assert r.raw_ref == "test-raw"  # 可追溯


def test_bb_leagues_empty_means_full():
    """回归: 空 leagues 配置({}) 不得回退成 8 大联赛(空 dict falsy bug)。"""
    a = BBAdapter(leagues={})
    assert a.leagues == {}
    # normalize 不依赖过滤, 任意联赛都应产生记录
    assert len(a.normalize(make_bb_match(), 1234)) == 2


def test_bb_leagues_filter():
    """leagues 过滤只发生在 fetch(网络层), normalize 不依赖过滤。"""
    a = BBAdapter(leagues={11020: "欧国联"})
    assert a.leagues == {11020: "欧国联"}
    assert len(a.normalize(make_bb_match(), 1234)) == 2
    a2 = BBAdapter(leagues={99999: "其他"})
    assert a2.leagues == {99999: "其他"}


def test_sx_pct_to_decimal_base20():
    """percentageOdds 基准 1e20: 4.6e19 => prob 0.46 => decimal ~2.174。"""
    assert abs(pct_to_decimal("46000000000000000000") - 2.1739) < 0.01


def test_sx_pct_fallback_lower_base():
    """主基准不适用时回退其他基准。"""
    # 1e18 基准: 4.6e17 => prob 0.46
    v = pct_to_decimal("460000000000000000")
    assert v is not None and 1.5 < v < 3


def test_sx_pct_invalid():
    assert pct_to_decimal("abc") is None
    assert pct_to_decimal("0") is None
    assert pct_to_decimal("") is None


def make_sx_bundle():
    """SX 真实 bundle 结构: {market, odds, received_at, raw_ref}。"""
    return {
        "market": {
            "sportXeventId": "evt1",
            "gameTime": 1791000000,
            "teamOneName": "Manchester United",
            "teamTwoName": "Chelsea",
            "type": "52",
            "marketHash": "0xabc",
            "outcomeOneName": "Manchester United",
            "outcomeTwoName": "Chelsea",
        },
        "odds": {
            "outcomeOne": [{"percentageOdds": "46000000000000000000", "size": "100"}],
            "outcomeTwo": [{"percentageOdds": "49875000000000000000", "size": "200"}],
        },
        "received_at": 1234,
        "raw_ref": "sx-raw-1",
    }


def test_sx_normalize_type52():
    a = SXBetAdapter()
    recs = a.normalize(make_sx_bundle(), raw_ref="sx-raw-1")
    assert len(recs) == 2
    assert all(r.source == "sx" for r in recs)
    assert all(r.market_type == "52" for r in recs)  # 源格式字符串
    assert any(r.option == "Manchester United" for r in recs)
    assert all(r.odds and r.odds > 1 for r in recs)
    assert all(r.raw_ref == "sx-raw-1" for r in recs)
