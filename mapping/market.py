from dataclasses import dataclass
from .status import MAPPED, UNMAPPED, INVALID
from .match import norm_name


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
    status: str = MAPPED


MTY = {
    # BB 源
    "1000": "asian_handicap",
    "1007": "over_under",
    "1005": "1x2",
    "1012": "double_chance",
    "1010": "corner_over_under",
    # SX 源
    "1": "binary",
    "2": "total",
    "3": "asian_handicap",
    "52": "1x2",
}

PE = {
    "1001": "full_time",
}

# 需要 line 的盘口类型(缺失 line 视为 INVALID)
LINE_REQUIRED = {"asian_handicap", "over_under", "total",
                 "corner_over_under"}


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
    """标准化 selection(规则 7.1/7.2/7.3): HOME/AWAY/OVER/UNDER/DRAW。

    - 英文队名精确/前缀匹配(SX)
    - 中文语义(主队/客队/主胜/客胜/大/小/和)(BB)
    仅做盘口语义标准化, 不涉及投资判断(规则 9.2 边界)。
    """
    if not option:
        return None
    o = str(option)
    if o == home:
        return "HOME"
    if o == away:
        return "AWAY"
    nh = norm_name(home)
    na = norm_name(away)
    no = norm_name(o)
    if nh and no.startswith(nh):
        return "HOME"
    if na and no.startswith(na):
        return "AWAY"
    if o.startswith(("主", "主队", "主胜")):
        return "HOME"
    if o.startswith(("客", "客队", "客胜")):
        return "AWAY"
    if "主胜" in o or "主队" in o:
        return "HOME"
    if "客胜" in o or "客队" in o:
        return "AWAY"
    if "和" in o or "平" in o:
        return "DRAW"
    if o.startswith(("大", "Over", "over")):
        return "OVER"
    if o.startswith(("小", "Under", "under")):
        return "UNDER"
    return None


def normalize(record):
    mtype = MTY.get(str(record.market_type), "unknown")
    period = PE.get(str(record.period), str(record.period)
                    if record.period else None)

    side = detect_side(record.option, record.home, record.away)

    line = record.line
    if line is None:
        line = parse_line(record.line_raw)

    # 显式状态(规则 7.4/34): 未知类型 -> UNMAPPED; 非法赔率/缺失必填 line -> INVALID
    status = MAPPED
    if mtype == "unknown":
        status = UNMAPPED
    elif record.odds is None or record.odds <= 0:
        status = INVALID
    elif mtype in LINE_REQUIRED and line is None:
        status = INVALID

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
        odds=record.odds,
        status=status,
    )
