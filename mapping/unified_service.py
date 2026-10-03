from .market import normalize
from .unified_db import save_unified
from .status import MAPPED
from core import env


def unify(record, canonical_match_id=None, conn=None):
    """归一化为 unified 快照。

    规则 7.4/34: 仅 MAPPED 盘口进入 unified_snapshots(下游唯一标准入口);
    UNMAPPED / INVALID 由调用方在 market_mappings 中显式标记, 不得静默混入。
    """
    market = normalize(record)
    pipeline_version = env.pipeline_version()

    if market.status == MAPPED:
        save_unified(
            type("UnifiedRecord", (), {
                "source": record.source,
                "bookmaker": record.bookmaker,
                "source_match_id": record.source_match_id,
                "source_market_id": market.source_market_id,
                "market_type": market.market_type,
                "period": market.period,
                "line_raw": market.line_raw,
                "line": market.line,
                "side": market.side,
                "option": market.option,
                "odds": market.odds,
                "event_time": record.event_time,
                "server_time": record.server_time,
                "received_at": record.received_at,
                "raw_ref": record.raw_ref,
                "pipeline_version": pipeline_version,
            })(),
            canonical_match_id=canonical_match_id,
            conn=conn,
        )

    return market
