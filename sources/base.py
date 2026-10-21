from dataclasses import dataclass
from typing import Optional

@dataclass
class NormalizedRecord:
    source: str
    bookmaker: Optional[str]
    source_match_id: str
    canonical_match_id: Optional[str]
    source_market_id: str
    market_type: str
    period: Optional[str]
    home: str
    away: str
    line_raw: Optional[str]
    line: Optional[float]
    option: str
    odds: Optional[float]
    event_time: Optional[int]
    server_time: Optional[int]
    received_at: int
    raw_ref: Optional[str] = None
    # Phase 4: Normalizer 版本化与证据(规格 §7.1/7.3)
    normalizer_name: str = ""
    normalizer_version: str = ""
    config_hash: str = ""
