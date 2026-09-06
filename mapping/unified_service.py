from .market import normalize
from .unified_db import save_unified

def unify(record, canonical_match_id=None):
    market=normalize(record)

    save_unified(
        type("UnifiedRecord",(),{
            "source":record.source,
            "bookmaker":record.bookmaker,
            "source_match_id":record.source_match_id,
            "source_market_id":market.source_market_id,
            "market_type":market.market_type,
            "period":market.period,
            "line_raw":market.line_raw,
            "line":market.line,
            "side":market.side,
            "option":market.option,
            "odds":market.odds,
            "event_time":record.event_time,
            "server_time":record.server_time,
            "received_at":record.received_at,
            "raw_ref":record.raw_ref
        })(),
        canonical_match_id=canonical_match_id
    )

    return market
