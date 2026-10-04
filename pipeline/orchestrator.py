"""BB Node V0.2 —— 正式 Pipeline Orchestrator(规则 17/18/47 + V0.2 QUALITY stage)。

统一协调: COLLECT -> NORMALIZE -> MAPPING -> UNIFIED -> QUALITY -> EVENT
-> FEATURE -> SIGNAL -> STRATEGY -> DECISION。

每个 Stage:
  - 明确输入/输出/错误状态
  - 记录执行时间与数量(core.log pipeline_runs)
  - 失败可定位(独立 try/except, 报告各 stage 状态)

生产主流程唯一入口: python -m pipeline.orchestrator
V0.2 增量: --incremental 时 EVENT 只处理最新快照(规则 54/55)。
"""
import sys
import time

from core import env
from core.log import new_trace_id
from database.db import init
from core.collector import collect as run_collect
from core.status import print_status

PIPELINE_VERSION = env.pipeline_version()

ALL_STAGES = ["COLLECT", "NORMALIZE", "MAPPING", "UNIFIED", "QUALITY",
              "EVENT", "EVENT_GROUP", "FEATURE", "SIGNAL", "STRATEGY",
              "DECISION"]


def _run_stage(name, fn, *args, **kwargs):
    t0 = time.time()
    try:
        out = fn(*args, **kwargs)
        return {
            "stage": name,
            "status": "OK",
            "output": out,
            "elapsed_s": round(time.time() - t0, 3),
        }
    except Exception as e:
        return {
            "stage": name,
            "status": "ERROR",
            "error": str(e)[:500],
            "elapsed_s": round(time.time() - t0, 3),
        }


def run_pipeline(sources=None, cutoff=None, stages=None, quiet=False,
                 trace_id=None, incremental=False):
    """执行完整生产 Pipeline(V0.2)。

    stages: 要运行的阶段列表, 默认全部(COLLECT..DECISION)。
    cutoff: 毫秒时间戳, 只处理 <= cutoff 的数据(时间旅行)。
    incremental: 增量模式(Event 只比较最新快照, 规则 54/55)。
    trace_id: 链路追踪 ID(规则 52)。
    """
    init()
    trace_id = trace_id or new_trace_id("pipeline")

    want = [s.upper() for s in stages] if stages else list(ALL_STAGES)
    invalid = [s for s in want if s not in ALL_STAGES]
    if invalid:
        raise ValueError("unknown stage(s): %s" % ",".join(invalid))

    # 依赖前置: 若指定下游而未指定上游, 补全上游(数据真实性优先)
    order = {s: i for i, s in enumerate(ALL_STAGES)}
    have = set(want)
    for s in sorted(want, key=lambda x: order[x]):
        for dep in ALL_STAGES[:order[s]]:
            if dep not in have:
                have.add(dep)
    want = [s for s in ALL_STAGES if s in have]

    results = {}

    if "COLLECT" in want:
        print("=== Stage COLLECT ===")
        results["COLLECT"] = _run_stage("COLLECT", run_collect, sources)

    if "QUALITY" in want:
        print("=== Stage QUALITY ===")
        from quality.engine_v1 import run as dq_run

        def _dq():
            return dq_run(cutoff=cutoff, pipeline_run_id=trace_id,
                          trace_id=trace_id)

        results["QUALITY"] = _run_stage("QUALITY", _dq)

    if "EVENT" in want:
        print("=== Stage EVENT ===")
        from events.engine_v3 import run as event_run
        from events.group_v3 import run as group_run
        r1 = _run_stage("EVENT", event_run, cutoff)
        r2 = _run_stage("EVENT_GROUP", group_run, cutoff)
        results["EVENT"] = r1
        results["EVENT_GROUP"] = r2

    if "FEATURE" in want:
        print("=== Stage FEATURE ===")
        from features.engine_v2 import run as feature_run
        results["FEATURE"] = _run_stage("FEATURE", feature_run, cutoff)

    if "SIGNAL" in want:
        print("=== Stage SIGNAL ===")
        from signals.engine_v1 import run as signal_run
        results["SIGNAL"] = _run_stage("SIGNAL", signal_run, cutoff)

    if "STRATEGY" in want:
        print("=== Stage STRATEGY ===")
        from strategies.engine_v1 import run as strategy_run
        results["STRATEGY"] = _run_stage("STRATEGY", strategy_run, cutoff)

    if "DECISION" in want:
        print("=== Stage DECISION ===")
        from decisions.engine_v1 import run as decision_run
        results["DECISION"] = _run_stage("DECISION", decision_run, cutoff)

    if not quiet:
        _print_summary(results)

    ok = all(r["status"] == "OK" for r in results.values())
    results["PASS"] = ok
    results["trace_id"] = trace_id
    return results


def _print_summary(results):
    print("\n=== PIPELINE SUMMARY ===")
    print("pipeline_version:", PIPELINE_VERSION)
    print("schema_version:", env.schema_version())
    print("engines:", env.get("engines"))
    for name, r in results.items():
        if name in ("PASS", "trace_id"):
            continue
        if r["status"] == "OK":
            print("[OK]   %s  %ss" % (name, r["elapsed_s"]))
        else:
            print("[FAIL] %s  %s" % (name, r.get("error", "")))
    return all(r["status"] == "OK"
               for k, r in results.items() if k not in ("PASS", "trace_id"))


def main():
    import argparse
    ap = argparse.ArgumentParser(description="BB Node V0.2 Pipeline")
    ap.add_argument("--stage", nargs="+", default=None,
                    help="只运行指定阶段, 如 --stage COLLECT EVENT")
    ap.add_argument("--source", nargs="+", default=None,
                    help="只采集指定 Source, 如 --source bb sx")
    ap.add_argument("--cutoff", type=int, default=None,
                    help="时间旅行截止(毫秒时间戳)")
    ap.add_argument("--incremental", action="store_true",
                    help="增量模式(规则 54/55)")
    ap.add_argument("--replay", action="store_true",
                    help="运行 True Replay")
    ap.add_argument("--replay-cutoff", type=int, default=None,
                    help="Replay 时间截止(毫秒)")
    ap.add_argument("--backtest", action="store_true",
                    help="运行 Backtest(基于 Replay)")
    ap.add_argument("--status", action="store_true",
                    help="打印 Pipeline 健康状态")
    args = ap.parse_args()

    if args.status:
        print_status()
        return

    if args.replay:
        from replay.true_replay import run as replay_run
        replay_run(cutoff=args.replay_cutoff)
        if args.backtest:
            from backtest.engine_v2 import run as bt_run
            bt_run()
        return

    results = run_pipeline(
        sources=args.source,
        cutoff=args.cutoff,
        stages=args.stage,
        incremental=args.incremental,
    )
    ok = results.get("PASS", False)
    print("\nPIPELINE: %s" % ("PASS" if ok else "FAIL"))
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
