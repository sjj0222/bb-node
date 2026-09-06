from dataclasses import dataclass

@dataclass
class MarketMapping:
    source: str
    source_market_id: str
    bookmaker: str | None
    source_match_id: str | None
    market_type: str
    period: str | None
    line_raw: str | None
    line: float | None
    side: str | None
    option: str
    odds: float | None

MTY = {
    "1000": "asian_handicap",
    "1007": "over_under",
    "1005": "1x2",
    "1012": "double_chance",
    "1010": "corner_over_under",
}

PE = {
    "1001": "full_time",
}

def parse_line(v):
    if v is None:
        return None

    s = str(v).strip()

    try:
        return float(s)
    except ValueError:
        pass

    if "/" in s:
        p = s.split("/")
        try:
            return (float(p[0]) + float(p[1])) / 2
        except ValueError:
            return None

    return None

def detect_side(option, home, away):
    if option == home:
        return "home"
    if option == away:
        return "away"
    return None

def normalize(record):
    mtype = MTY.get(str(record.market_type), "unknown")
    period = PE.get(str(record.period), str(record.period) if record.period else None)

    side = detect_side(
        record.option,
        record.home,
        record.away
    )

    line = record.line

    if line is None:
        line = parse_line(record.line_raw)

    return MarketMapping(
        source=record.source,
        source_market_id=record.source_market_id,
        bookmaker=record.bookmaker,
        source_match_id=record.source_match_id,
        market_type=mtype,
        period=period,
        line_raw=record.line_raw,
        line=line,
        side=side,
        option=record.option,
        odds=record.odds
    )
