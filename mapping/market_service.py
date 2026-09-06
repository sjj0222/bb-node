from .market import normalize
from .market_db import save_market

def map_and_save(record, canonical_match_id=None):
    m=normalize(record)

    save_market(
        m,
        canonical_match_id=canonical_match_id,
        source_match_id=record.source_match_id
    )

    return m
