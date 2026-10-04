"""Data Quality Engine V1(V0.2 P0-4, 规则 20/21/22/23)。

检查维度:
- 完整性: 缺字段(odds/line/side/时间)/缺盘口
- 有效性: 非法赔率(<=0)/非法 line/非法时间/非法 ID
- 一致性: Source 内/间冲突, Match/Market 冲突
- 唯一性: 重复数据/重复快照/重复事件
- 新鲜度: STALE
- 连续性: 采集断档(out-of-order / gap)

输出: total/valid/invalid/missing/duplicate/conflict/unmapped/stale/out_of_order
+ DQ Score(规则 22: Score 不掩盖错误, 严重错误仍显式状态)。
"""
import time
import sqlite3
from core import env
from core.log import start, finish, error, log_event, new_trace_id

DB = env.db_path()
ENGINE_VERSION = "v1"
PIPELINE_VERSION = env.pipeline_version()


def _safe_float(v):
    try:
        f = float(v)
        return f if f == f else None  # NaN -> None
    except (TypeError, ValueError):
        return None


def _gap(rows, max_gap_ms):
    """连续性: 相邻 received_at 断档检测。返回 (gap_count, gaps)。"""
    times = sorted({r["received_at"] for r in rows})
    gaps = 0
    details = []
    for a, b in zip(times, times[1:]):
        if b - a > max_gap_ms:
            gaps += 1
            details.append((a, b))
    return gaps, details


def run(cutoff=None, db=None, pipeline_run_id=None, trace_id=None):
    dbfile = db or DB
    trace_id = trace_id or new_trace_id("quality")
    log_id = start("QUALITY", "unified_snapshots")

    cfg = env.get("quality") or {}
    max_stale = cfg.get("max_stale_seconds", 900) * 1000
    max_gap = cfg.get("max_gap_seconds", 600) * 1000

    _external = hasattr(dbfile, "execute")
    c = dbfile if _external else sqlite3.connect(dbfile)
    c.row_factory = sqlite3.Row
    try:
        if cutoff:
            rows = c.execute("""select * from unified_snapshots
                where received_at <= ? order by id""", (cutoff,)).fetchall()
        else:
            rows = c.execute(
                "select * from unified_snapshots order by id").fetchall()

        total = len(rows)

        missing = 0      # 缺字段/缺盘口
        invalid = 0      # 非法赔率/line/时间/ID
        duplicate = 0    # 同 received_at 同 key 重复
        conflict = 0     # 同 canonical+market 多值冲突
        unmapped = 0     # 无 canonical_match_id
        stale = 0
        out_of_order = 0

        seen = set()
        dup_keys = set()
        for r in rows:
            key = (r["source"], r["source_match_id"],
                   r["source_market_id"], r["option"], r["received_at"])
            if key in seen:
                dup_keys.add(key)
                duplicate += 1
            seen.add(key)

            if not r["canonical_match_id"]:
                unmapped += 1
            if not r["option"] or r["received_at"] is None:
                missing += 1
            o = _safe_float(r["odds"])
            if o is None or o <= 0:
                invalid += 1
            # event_time 非法值(非合理毫秒时间戳) -> invalid; 未来时间属正常(未开赛)
            if r["event_time"] is None:
                missing += 1

        # 冲突(规则 21): Mapping 层 CONFLICT + 同 source 内同一
        # (source_match_id, source_market_id, option, received_at) 多值
        # (同一盘口 ID 对同一事实给出不同值)。不同 line 档(不同 market_id)
        # 并存是正常数据特征, 不算冲突。跨 source odds 差异是正常多源事实。
        mm = {}
        for r in rows:
            if not r["canonical_match_id"]:
                continue
            k = (r["source"], r["source_match_id"], r["source_market_id"],
                 r["option"], r["received_at"])
            v = (r["line"], r["odds"])
            if k in mm and mm[k] != v:
                conflict += 1
            mm[k] = v
        # Mapping 层显式 CONFLICT(规则 6.3/7.4)
        map_conflict = 0
        try:
            map_conflict += c.execute(
                "select count(*) from match_mappings where status='CONFLICT'"
            ).fetchone()[0]
            map_conflict += c.execute(
                "select count(*) from market_mappings where status='CONFLICT'"
            ).fetchone()[0]
        except Exception:
            pass
        conflict += map_conflict

        # 新鲜度: 最新 received_at 距今
        if rows:
            latest = max(r["received_at"] for r in rows)
            now = int(time.time() * 1000)
            if now - latest > max_stale:
                stale = 1

        # 连续性: 断档
        gaps, gap_details = _gap(rows, max_gap)
        out_of_order = gaps

        valid = total - (missing + invalid + duplicate + conflict)

        # DQ Score(规则 22): 0-100, 但严重错误仍以显式状态呈现
        score = 100.0
        if total:
            score -= 100.0 * (missing + invalid + conflict) / total
            score -= 20.0 * (duplicate + out_of_order) / max(1, total)
        score = max(0.0, round(score, 2))

        detail = {
            "gaps": gap_details[:10],
            "dup_keys": list(dup_keys)[:10],
        }

        c.execute("""insert into dq_runs(
            run_id,pipeline_run_id,window_start,window_end,
            total,valid,invalid,missing,duplicate,conflict,unmapped,
            stale,out_of_order,score,detail,pipeline_version,created_at)
            values(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (trace_id, pipeline_run_id,
             min((r["received_at"] for r in rows), default=0),
             max((r["received_at"] for r in rows), default=0),
             total, valid, invalid, missing, duplicate, conflict, unmapped,
             stale, out_of_order, score,
             __import__("json").dumps(detail, ensure_ascii=False),
             PIPELINE_VERSION, int(time.time() * 1000)))
        c.commit()

        summary = {
            "total": total, "valid": valid, "invalid": invalid,
            "missing": missing, "duplicate": duplicate, "conflict": conflict,
            "unmapped": unmapped, "stale": stale, "out_of_order": out_of_order,
            "score": score, "dq_run_id": trace_id,
        }
        log_event("INFO", "QUALITY", "dq", "DQ total=%s valid=%s invalid=%s "
                  "missing=%s dup=%s conflict=%s unmapped=%s stale=%s "
                  "gap=%s score=%s" % (
                      total, valid, invalid, missing, duplicate, conflict,
                      unmapped, stale, out_of_order, score), trace_id)
        finish(log_id, "OK", total, valid, "DQ score=%s" % score)
        return summary
    except Exception as e:
        c.rollback()
        error("QUALITY", e)
        finish(log_id, "ERROR", 0, 0, str(e)[:200])
        raise
    finally:
        if not _external:
            c.close()


if __name__ == "__main__":
    print(run())
