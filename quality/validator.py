"""Phase 4: 校验层次(规格 §7.2)。

结构 -> 语义 -> 时间。校验失败不静默丢弃:
由 collector 写入 quality_errors(拒绝表/错误队列), 可从 RAW 重放。

校验器只报错, 不修改记录值(缺失/异常值不被伪造)。
"""
import math

# 层
STRUCTURE = "STRUCTURE"
SEMANTIC = "SEMANTIC"
TIME = "TIME"

# 错误码
MISSING_FIELD = "MISSING_FIELD"
BAD_TYPE = "BAD_TYPE"
ODDS_MISSING = "ODDS_MISSING"
ODDS_OUT_OF_RANGE = "ODDS_OUT_OF_RANGE"
LINE_INVALID = "LINE_INVALID"
TIME_ORDER = "TIME_ORDER"

# 语义阈值(规格: 赔率取值合理; 过小/过大视为异常, 不伪造)
ODDS_MIN = 1.01
ODDS_MAX = 50.0
# 源时间允许晚于抓取时间的容差(ms)
TIME_TOLERANCE_MS = 10 * 60 * 1000


def _is_num(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def validate(rec):
    """返回 [(layer, code, message), ...]; 无问题返回 []。"""
    errs = []

    # ---- 结构层: 字段存在、类型正确 ----
    for field, val in (
        ("source_match_id", rec.source_match_id),
        ("source_market_id", rec.source_market_id),
        ("market_type", rec.market_type),
        ("home", rec.home),
        ("away", rec.away),
        ("option", rec.option),
    ):
        if val is None:
            errs.append((STRUCTURE, MISSING_FIELD,
                         "missing field %s" % field))

    if rec.home is not None and not isinstance(rec.home, str):
        errs.append((STRUCTURE, BAD_TYPE, "home not str"))
    if rec.away is not None and not isinstance(rec.away, str):
        errs.append((STRUCTURE, BAD_TYPE, "away not str"))
    if rec.option is not None and not isinstance(rec.option, str):
        errs.append((STRUCTURE, BAD_TYPE, "option not str"))
    if rec.market_type is not None and not isinstance(rec.market_type, str):
        errs.append((STRUCTURE, BAD_TYPE, "market_type not str"))
    if rec.received_at is not None and not _is_num(rec.received_at):
        errs.append((STRUCTURE, BAD_TYPE, "received_at not numeric"))

    # ---- 语义层: 取值合理 ----
    if rec.odds is None:
        errs.append((SEMANTIC, ODDS_MISSING, "odds missing"))
    elif not _is_num(rec.odds) or math.isnan(rec.odds):
        errs.append((SEMANTIC, BAD_TYPE, "odds not numeric"))
    elif rec.odds < ODDS_MIN or rec.odds > ODDS_MAX:
        errs.append((SEMANTIC, ODDS_OUT_OF_RANGE,
                     "odds %.4f out of [%.2f, %.2f]"
                     % (rec.odds, ODDS_MIN, ODDS_MAX)))

    if rec.line is not None:
        if not _is_num(rec.line) or math.isnan(rec.line):
            errs.append((SEMANTIC, LINE_INVALID, "line not numeric"))
        elif math.isinf(rec.line):
            errs.append((SEMANTIC, LINE_INVALID, "line infinite"))

    # ---- 时间层: 抓取时间不得早于源时间(容差内) ----
    if rec.server_time is not None and rec.received_at is not None:
        if rec.server_time > rec.received_at + TIME_TOLERANCE_MS:
            errs.append((TIME, TIME_ORDER,
                         "server_time %s > received_at %s"
                         % (rec.server_time, rec.received_at)))

    return errs
