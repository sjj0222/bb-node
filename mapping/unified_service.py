from .market import normalize
from .unified_db import save_unified
from .status import MAPPED
from core import env


def _unified_record(record, market, pipeline_version):
    """由 record(来源时间/引用) + market(归一化结果) 构造统一快照输入。"""
    return type("UnifiedRecord", (), {
        "source": record.source,
        "bookmaker": record.bookmaker,
        "source_match_id": record.source_match_id,
        "source_market_id": market.source_market_id,
        "market_type": market.market_type,
        "period": market.period,
        "line_raw": market.line_raw,
        "line": market.line,
        "line_quarters": market.line_quarters,
        "side": market.side,
        "option": market.option,
        "odds": market.odds,
        "odds_raw": market.odds_raw,
        "event_time": record.event_time,
        "server_time": record.server_time,
        "received_at": record.received_at,
        "raw_ref": record.raw_ref,
        "league_id": getattr(record, "league_id", None),
        "pipeline_version": pipeline_version,
    })()


def unify(record, canonical_match_id=None, conn=None):
    """归一化为 unified 快照。

    规则 7.4/34: 仅 MAPPED 盘口进入 unified_snapshots(下游唯一标准入口);
    UNMAPPED / INVALID 由调用方在 market_mappings 中显式标记, 不得静默混入。
    """
    market = normalize(record)
    return unify_market(record, market,
                        canonical_match_id=canonical_match_id, conn=conn)


def unify_market(record, market, canonical_match_id=None, conn=None):
    """P3-18: 复用调用方已归一化的 market, 不再二次 normalize。

    此前 collector 先 map_and_save()(内部 normalize 一次) 再 unify()
    (又 normalize 一次)——纯浪费且两次结果理论上可能不一致。
    """
    pipeline_version = env.pipeline_version()
    if market.status == MAPPED:
        save_unified(
            _unified_record(record, market, pipeline_version),
            canonical_match_id=canonical_match_id,
            conn=conn,
        )
    return market
