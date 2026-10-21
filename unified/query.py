"""Phase 7: Unified 查询服务(规格 §9)。

- query_unified: 按赛事/联赛/来源/市场类型/周期/主客队/盘口线/新鲜度/
  映射状态过滤
- latest_quotes: 最新值视图(规格 §9.2, 视图不是历史替代)
- market_series: 盘口时间序列
- cross_source_compare: 同一赛事不同来源报价对比(保留每个来源独立报价,
  不做平均覆盖)
- plan_report: EXPLAIN QUERY PLAN 基线报告(查询性能可审计)
"""
import json
import time


def query_unified(conn, *, match_id=None, league=None, source=None,
                  market_type=None, period=None, side=None, line=None,
                  min_odds=None, max_odds=None, fresh_ms=None,
                  mapping_status=None, superseded=False, limit=500):
    sql = "SELECT * FROM unified_snapshots WHERE 1=1"
    args = []
    if match_id:
        sql += " AND canonical_match_id=?"
        args.append(match_id)
    if league:
        sql += " AND league_id=?"
        args.append(int(league))
    if source:
        sql += " AND source=?"
        args.append(source)
    if market_type:
        sql += " AND market_type=?"
        args.append(market_type)
    if period:
        sql += " AND period=?"
        args.append(period)
    if side:
        sql += " AND side=?"
        args.append(side)
    if line is not None:
        sql += " AND line=?"
        args.append(float(line))
    if min_odds is not None:
        sql += " AND odds>=?"
        args.append(float(min_odds))
    if max_odds is not None:
        sql += " AND odds<=?"
        args.append(float(max_odds))
    if not superseded:
        sql += " AND superseded=0"
    if fresh_ms:
        sql += " AND received_at>=?"
        args.append(int(time.time() * 1000) - int(fresh_ms))
    if mapping_status:
        sql += (" AND canonical_match_id IS NOT NULL" if
                mapping_status == "mapped" else
                " AND canonical_match_id IS NULL")
    sql += " ORDER BY received_at DESC, id DESC LIMIT %d" % int(limit)
    return [dict(r) for r in conn.execute(sql, args)]


def latest_quotes(conn, *, match_id=None, source=None, market_type=None,
                  limit=500):
    """最新值视图(规格 §9.2)。"""
    sql = ("SELECT * FROM latest_unified_quotes WHERE 1=1")
    args = []
    if match_id:
        sql += " AND canonical_match_id=?"
        args.append(match_id)
    if source:
        sql += " AND source=?"
        args.append(source)
    if market_type:
        sql += " AND market_type=?"
        args.append(market_type)
    sql += " ORDER BY canonical_match_id, source, market_type LIMIT %d" % int(limit)
    return [dict(r) for r in conn.execute(sql, args)]


def market_series(conn, canonical_match_id, market_type, period=None,
                  limit=1000):
    """盘口时间序列(按观测时间升序, 追加而非覆盖, 规格 §9.2/9.3)。"""
    sql = ("SELECT * FROM unified_snapshots "
           "WHERE canonical_match_id=? AND market_type=? AND superseded=0")
    args = [canonical_match_id, market_type]
    if period:
        sql += " AND period=?"
        args.append(period)
    sql += " ORDER BY received_at ASC, id ASC LIMIT %d" % int(limit)
    return [dict(r) for r in conn.execute(sql, args)]


def cross_source_compare(conn, canonical_match_id, market_type,
                         period=None):
    """同一赛事同一市场定义: 每来源最新报价并列(不平均覆盖原值)。

    period 默认不限(来源周期口径可能不同: bb='0'/None, sx=None);
    指定时精确匹配。
    """
    if period:
        sql = ("SELECT * FROM latest_unified_quotes "
               "WHERE canonical_match_id=? AND market_type=? AND period=?"
               "ORDER BY source, line, option")
        args = (canonical_match_id, market_type, period)
    else:
        sql = ("SELECT * FROM latest_unified_quotes "
               "WHERE canonical_match_id=? AND market_type=?"
               "ORDER BY source, line, option")
        args = (canonical_match_id, market_type)
    return [dict(r) for r in conn.execute(sql, args)]


def plan_report(conn, samples=None):
    """EXPLAIN QUERY PLAN 基线: 记录关键查询的执行计划(性能可审计)。"""
    samples = samples or [
        ("latest_by_match", "latest_unified_quotes",
         "SELECT * FROM latest_unified_quotes WHERE canonical_match_id=?",
         ["cm_test"]),
        ("series", "unified_snapshots",
         "SELECT * FROM unified_snapshots WHERE canonical_match_id=? "
         "AND market_type=? AND superseded=0 ORDER BY received_at ASC",
         ["cm_test", "asian_handicap"]),
        ("league_filter", "unified_snapshots",
         "SELECT * FROM unified_snapshots WHERE league_id=? AND superseded=0",
         [11062]),
    ]
    out = []
    for name, _tbl, sql, args in samples:
        rows = conn.execute(
            "EXPLAIN QUERY PLAN " + sql.replace("?", "'cm_x'")).fetchall()
        plan = [dict(r) for r in rows]
        out.append({"name": name, "sql": sql, "plan": plan,
                    "plan_lines": ["%s | %s | %s | %s" % (
                        r["id"], r["parent"], r["notused"],
                        r["detail"]) for r in rows]})
    return out
