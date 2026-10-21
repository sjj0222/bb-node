"""Phase 10: Replay 与 Backtest(规格 §11)。

Replay:
  - 默认按 observed_at(recorded_at) 重建系统当时实际看见的数据;
    按源事件时间回放时 mode='event_time' 单独标明
  - 稳定排序 tie-breaker: (event_time, recorded_at, event_id)
  - 相同快照/版本/范围 -> 可复现结果
  - 输出与生产表隔离(replay_events); 失败任务清理临时结果, 不碰生产

Backtest:
  - 严格时间切分: train/test 不混用; 特征 as_of 无未来泄漏
  - 保存规则版本/参数/范围/随机种子
  - 输出样本数/覆盖率/命中/缺失处理/分组/口径声明
"""
import json
import time
import uuid

from signals.rules import get_rule, evaluate as rule_evaluate


# ---------- Replay ----------

def replay_run(conn, *, name, start_ms, end_ms, mode="observed_at",
               version="replay-v1", code_version="bb-node-v1",
               event_types=None, persist=True):
    """执行一次回放, 输出隔离在 replay_events(生产 events 不动)。"""
    if mode not in ("observed_at", "event_time"):
        raise ValueError("mode must be observed_at or event_time")
    run_id = "rp_%s" % uuid.uuid4().hex[:12]
    now = int(time.time() * 1000)
    conn.execute("""INSERT INTO replay_runs(
        run_id, name, mode, start_ms, end_ms, version, code_version,
        started_at, status)
        VALUES(?,?,?,?,?,?,?,?,'running')""",
                 (run_id, name, mode, int(start_ms), int(end_ms), version,
                  code_version, now))
    try:
        time_col = "recorded_at" if mode == "observed_at" else "event_time"
        sql = ("SELECT * FROM events WHERE %s>=? AND %s<=?" % (time_col,
                                                               time_col))
        args = [int(start_ms), int(end_ms)]
        if event_types:
            sql += " AND event_type IN (%s)" % ",".join("?" * len(event_types))
            args.extend(event_types)
        sql += " ORDER BY event_time ASC, recorded_at ASC, id ASC"
        rows = conn.execute(sql, args).fetchall()
        for seq, row in enumerate(rows, start=1):
            conn.execute("""INSERT INTO replay_events(
                run_id, seq, event_id, event_type, entity_key, event_time,
                recorded_at, payload)
                VALUES(?,?,?,?,?,?,?,?)""",
                         (run_id, seq, row["id"], row["event_type"],
                          row["entity_key"], row["event_time"],
                          row["recorded_at"], row["payload"]))
        summary = {
            "mode": mode, "events": len(rows),
            "range_ms": [int(start_ms), int(end_ms)],
            "order": "event_time, recorded_at, event_id",
            "note": "replay 输出与生产表隔离",
        }
        conn.execute("""UPDATE replay_runs
            SET status='finished', finished_at=?, summary=?
            WHERE run_id=?""", (int(time.time() * 1000),
                                json.dumps(summary, ensure_ascii=False),
                                run_id))
        if persist:
            conn.commit()
        return {"run_id": run_id, "summary": summary}
    except Exception as exc:
        conn.execute("""UPDATE replay_runs
            SET status='failed', finished_at=?, summary=?
            WHERE run_id=?""", (int(time.time() * 1000),
                                json.dumps({"error": repr(exc)}), run_id))
        # 失败清理临时结果, 不碰生产 events
        conn.execute("DELETE FROM replay_events WHERE run_id=?", (run_id,))
        if persist:
            conn.commit()
        raise


def replay_results(conn, run_id):
    return [dict(r) for r in conn.execute(
        "SELECT * FROM replay_events WHERE run_id=? ORDER BY seq",
        (run_id,))]


# ---------- Backtest ----------

def _sample_matches(conn, start_ms, end_ms):
    """窗口内出现报价的赛事(去重)。"""
    rows = conn.execute("""
        SELECT DISTINCT canonical_match_id FROM unified_snapshots
        WHERE canonical_match_id IS NOT NULL AND superseded=0
          AND received_at>=? AND received_at<=?
    """, (int(start_ms), int(end_ms))).fetchall()
    return [r[0] for r in rows]


def backtest(conn, *, rule_id, version, train_start, train_end,
             test_start, test_end, params=None, seed=None, persist=True):
    """严格时间切分回测(训练/测试不混用, 特征 as_of 无泄漏)。"""
    if int(test_start) < int(train_end):
        raise ValueError("test_start must be >= train_end (strict split)")
    rule = get_rule(rule_id)
    run_id = "bt_%s" % uuid.uuid4().hex[:12]
    now = int(time.time() * 1000)

    def _window(lo, hi, label):
        matches = _sample_matches(conn, lo, hi)
        evaluated, missing, fired = 0, 0, 0
        by_group = {}
        for m in matches:
            # 决策时点 = 窗口末端(只用此时点前可获数据, 无未来泄漏)
            res = rule_evaluate(conn, rule_id, m, hi)
            if res["status"] == "invalidated":
                missing += 1          # 缺失 -> 剔除并报告, 不静默填补
                continue
            evaluated += 1
            out = res["output"] or {}
            if out.get("fired"):
                fired += 1
            g = by_group.setdefault(label + "_group", {"n": 0, "fired": 0})
            g["n"] += 1
            if out.get("fired"):
                g["fired"] += 1
        return {"label": label, "range_ms": [int(lo), int(hi)],
                "samples": len(matches), "evaluated": evaluated,
                "missing_excluded": missing, "fired": fired,
                "coverage": round(evaluated / len(matches), 4)
                if matches else 0.0}

    train = _window(int(train_start), int(train_end), "train")
    test = _window(int(test_start), int(test_end), "test")
    summary = {
        "rule_id": rule_id, "rule_version": version,
        "params": params or {},
        "seed": seed,
        "strict_split": [int(train_start), int(train_end),
                         int(test_start), int(test_end)],
        "windows": [train, test],
        "notes": [
            "特征只使用决策时点(as_of=窗口末端)以前的数据, 无未来泄漏",
            "数据缺失或不可比 -> 剔除并报告, 不静默填补",
            "回测不代表未来收益保证; 结果受样本偏差与数据源局限",
        ],
    }
    conn.execute("""INSERT INTO backtest_runs(
        run_id, rule_id, version, train_start, train_end, test_start,
        test_end, params, seed, summary, status, created_at)
        VALUES(?,?,?,?,?,?,?,?,?,?,'finished',?)""",
                 (run_id, rule_id, version, int(train_start),
                  int(train_end), int(test_start), int(test_end),
                  json.dumps(params or {}, ensure_ascii=False),
                  json.dumps(seed) if seed is not None else None,
                  json.dumps(summary, ensure_ascii=False), now))
    if persist:
        conn.commit()
    return {"run_id": run_id, "summary": summary}
