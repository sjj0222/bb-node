"""测试共享辅助: 构造两轮真实代码路径的 unified 数据。"""
from sources.base import NormalizedRecord
from mapping.service import auto_map
from mapping.market_service import map_and_save
from mapping.unified_service import unify


def nrec(source, smid, mmid, mtype, line_raw, option, odds, received_at, **kw):
    base = dict(
        source=source, bookmaker=source.upper(),
        source_match_id=smid, canonical_match_id=None,
        source_market_id=mmid,
        market_type=mtype, period="0", line_raw=line_raw,
        line=None, option=option, odds=odds,
        home="Manchester United", away="Chelsea",
        event_time=1000, server_time=1000, received_at=received_at,
        raw_ref=f"raw-{source}-{received_at}-{mmid}",
    )
    base.update(kw)
    return NormalizedRecord(**base)


def seed_round(conn, received_at, ah_line, ou_odds, ah_odds=1.90,
               ah_away_odds=None):
    """写入一轮 unified(2 场比赛 x 3-4 盘口)。

    ah_away_odds: 客队让球选项水位(默认 None = 不写客队选项)
    """
    if ah_away_odds is None:
        ah_away = []
    else:
        ah_away = [nrec("bb", "m1", "mm1b", "1000", ah_line,
                        "客队+%s" % ah_line.lstrip("-"),
                        ah_away_odds, received_at)]
    recs = [
        nrec("bb", "m1", "mm1", "1000", ah_line, "主队-0.5", ah_odds, received_at),
        nrec("bb", "m1", "mm2", "1007", "2.5", "大", ou_odds, received_at),
        nrec("sx", "e2", "mx1", "3", "-0.5", "Manchester United -0.5", 2.05, received_at),
        nrec("sx", "e2", "mx2", "2", "1.5", "Over 1.5", 1.72, received_at),
    ] + ah_away
    for r in recs:
        mm = auto_map(r, r, conn=conn)
        cid = mm["canonical_match_id"]
        assert mm["status"] == "MAPPED", mm
        mkt = map_and_save(r, canonical_match_id=cid, conn=conn)
        assert mkt.status == "MAPPED", mkt.status
        unify(r, cid, conn=conn)
    conn.commit()
