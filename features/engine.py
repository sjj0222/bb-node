"""Phase 9: 特征引擎(规格 §10.2)。

- 每个特征: 名称/版本/输入定义/窗口/空值策略/计算公式/输出类型/测试样例
- as_of_time 语义: 只使用该时点以前可获得的数据(received_at <= as_of)
- 空值策略: 默认 'absent'(缺失即特征缺失, 不填 0), 除非规范明确
- 计算失败记录原因(feature_errors), 不静默返回 0
- 版本化结果: 键含 version, 旧版结果不被新版静默覆盖
"""
import json
import statistics
import time

FEATURES = {}


def define_feature(name, version, inputs, window_ms, null_policy, formula,
                   output_type, test_cases=None):
    FEATURES[name] = {
        "name": name, "version": version, "inputs": inputs,
        "window_ms": window_ms, "null_policy": null_policy,
        "formula": formula, "output_type": output_type,
        "test_cases": test_cases or [],
    }
    return FEATURES[name]


def get_feature(name):
    f = FEATURES.get(name)
    if f is None:
        raise KeyError("unknown feature: %s" % name)
    return f


# ---------- 数据访问助手(as_of 语义) ----------

def quote_at(conn, match_id, *, source, market_type, period=None,
             side=None, line=None, as_of_time=None):
    """as_of 时点可见的最新报价(received_at <= as_of_time)。

    period 默认不限(来源周期口径不同: bb='0', sx=None);
    指定时按 COALESCE 精确匹配。
    """
    sql = ("""SELECT * FROM unified_snapshots
              WHERE canonical_match_id=? AND source=? AND market_type=?
                AND superseded=0""")
    args = [match_id, source, market_type]
    if period is not None:
        sql += " AND COALESCE(period,'')=COALESCE(?,'')"
        args.append(period)
    if side:
        sql += " AND side=?"
        args.append(side)
    if line is not None:
        sql += " AND line=?"
        args.append(float(line))
    if as_of_time is not None:
        sql += " AND received_at<=?"
        args.append(int(as_of_time))
    sql += " ORDER BY received_at DESC, id DESC LIMIT 1"
    row = conn.execute(sql, args).fetchone()
    return dict(row) if row else None


# ---------- 内置特征 ----------

define_feature(
    name="ah_odds_spread",
    version="ah-spread-v1",
    inputs=["bb home odds", "bb away odds"],
    window_ms=None,
    null_policy="absent",
    formula="(home_odds - away_odds) at as_of_time",
    output_type="float",
    test_cases=[],
)


def _compute_ah_odds_spread(ctx):
    conn, match_id, as_of = ctx["conn"], ctx["match_id"], ctx["as_of_time"]
    home = quote_at(conn, match_id, source="bb",
                    market_type="asian_handicap", side="HOME",
                    as_of_time=as_of)
    away = quote_at(conn, match_id, source="bb",
                    market_type="asian_handicap", side="AWAY",
                    as_of_time=as_of)
    if home is None or away is None:
        return None   # 空值策略 absent: 缺失即缺失
    return round(float(home["odds"]) - float(away["odds"]), 6)


define_feature(
    name="odds_volatility_30m",
    version="odds-vol-v1",
    inputs=["bb home odds series"],
    window_ms=30 * 60 * 1000,
    null_policy="absent",
    formula="std(home odds) within 30min before as_of_time",
    output_type="float",
    test_cases=[],
)


def _compute_odds_volatility(ctx):
    conn, match_id, as_of = ctx["conn"], ctx["match_id"], ctx["as_of_time"]
    rows = conn.execute("""
        SELECT odds FROM unified_snapshots
        WHERE canonical_match_id=? AND source='bb'
          AND market_type='asian_handicap' AND side='HOME'
          AND superseded=0 AND received_at<=?
          AND received_at>=?
        ORDER BY received_at ASC
    """, (match_id, int(as_of), int(as_of) - 30 * 60 * 1000)).fetchall()
    vals = [float(r[0]) for r in rows if r[0] is not None]
    if len(vals) < 2:
        return None
    return round(statistics.pstdev(vals), 6)


def compute_feature(conn, name, match_id, as_of_time, persist=True):
    """计算特征; 失败记录原因并返回 None(不默认 0)。"""
    try:
        f = get_feature(name)
    except KeyError:
        now = int(time.time() * 1000)
        conn.execute("""INSERT INTO feature_errors(
            feature_name, version, match_id, as_of_time, error, computed_at)
            VALUES(?,?,?,?,?,?)""",
                     (name, "", match_id, int(as_of_time),
                      "unknown feature", now))
        if persist:
            conn.commit()
        return None
    ctx = {"conn": conn, "match_id": match_id, "as_of_time": int(as_of_time)}
    now = int(time.time() * 1000)
    fn = _FORMULAS.get(name)
    if fn is None:
        conn.execute("""INSERT INTO feature_errors(
            feature_name, version, match_id, as_of_time, error, computed_at)
            VALUES(?,?,?,?,?,?)""",
                     (name, f["version"], match_id, int(as_of_time),
                      "no formula", now))
        if persist:
            conn.commit()
        return None
    try:
        value = fn(ctx)
    except Exception as exc:            # 计算失败记录原因
        conn.execute("""INSERT INTO feature_errors(
            feature_name, version, match_id, as_of_time, error, computed_at)
            VALUES(?,?,?,?,?,?)""",
                     (name, f["version"], match_id, int(as_of_time),
                      repr(exc), now))
        if persist:
            conn.commit()
        return None
    # 版本化: 键含 version, 旧版结果保留不覆盖
    conn.execute("""
        INSERT INTO feature_results(
            feature_name, version, match_id, as_of_time, value, error,
            computed_at)
        VALUES(?,?,?,?,?,?,?)
        ON CONFLICT(feature_name, version, match_id, as_of_time)
        DO UPDATE SET value=excluded.value, error=excluded.error,
                      computed_at=excluded.computed_at
    """, (name, f["version"], match_id, int(as_of_time),
          json.dumps(value) if value is not None else None, None, now))
    if persist:
        conn.commit()
    return value


_FORMULAS = {
    "ah_odds_spread": _compute_ah_odds_spread,
    "odds_volatility_30m": _compute_odds_volatility,
}


def latest_feature(conn, name, match_id, as_of_time):
    row = conn.execute("""
        SELECT * FROM feature_results
        WHERE feature_name=? AND match_id=? AND as_of_time=?
        ORDER BY computed_at DESC LIMIT 1
    """, (name, match_id, int(as_of_time))).fetchone()
    if row is None:
        return None
    d = dict(row)
    if d.get("value"):
        try:
            d["value"] = json.loads(d["value"])
        except (TypeError, ValueError):
            pass
    return d
