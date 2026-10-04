"""BB Node V0.2 统一 CLI(规则 50)。

命令:
  pipeline run|status [--source bb sx] [--stage ...] [--incremental]
  monitor start|stop|status|restart|once [--interval N]
  monitor add|remove|list <canonical_match_id>
  source list|status [name]
  market list
  node id|status|peers
  p2p export <obj> <cursor> <path> | p2p sync <obj> <path>
  replay run [--cutoff MS] [--source ...] [--match ...]
  backtest run [--group-by match|market|source|strategy|time|version]
  quality run
"""
import sys
import argparse


def _cmd_pipeline(args):
    from pipeline.orchestrator import run_pipeline, main as p_main
    if args.sub == "status":
        from core.status import print_status
        print_status()
        return
    results = run_pipeline(sources=args.source, stages=args.stage,
                           incremental=args.incremental)
    print("PIPELINE:", "PASS" if results.get("PASS") else "FAIL")


def _cmd_monitor(args):
    from monitor.monitor import Monitor
    from monitor import watchlist
    if args.sub in ("add", "remove", "list", "watchlist"):
        if args.sub == "add":
            watchlist.add(args.match, note=args.note or "")
            print("added", args.match)
        elif args.sub == "remove":
            watchlist.remove(args.match)
            print("removed", args.match)
        else:
            for w in watchlist.status():
                print(w)
        return
    m = Monitor(interval_seconds=args.interval)
    if args.sub == "start":
        print(m.start())
    elif args.sub == "stop":
        print(m.stop())
    elif args.sub == "restart":
        print(m.restart())
    elif args.sub == "once":
        print("round ok:", m.run_once())
    else:
        print(m.status())


def _cmd_source(args):
    from core import health
    if args.sub == "status":
        if args.name:
            print(health.status_of(args.name))
        else:
            for h in health.list_all():
                print(h["source"], h["status"],
                      "last_success=%s records=%s errors=%s" % (
                          h["last_success"], h["records"], h["error_count"]))
    else:
        cfg = env_sources()
        for name, meta in cfg.items():
            print(name, "enabled=%s" % meta.get("enabled", True))


def env_sources():
    from core import env
    return env.get("sources") or {}


def _cmd_market(args):
    from market.registry import REGISTRY
    for mt, handler in REGISTRY.list().items():
        print(mt, "->", handler)


def _cmd_node(args):
    from p2p import node
    if args.sub == "id":
        print(node.register_node())
    elif args.sub == "status":
        c = node.connect()
        rows = c.execute("select * from nodes_v2").fetchall()
        c.close()
        for r in rows:
            print(dict(r))
    elif args.sub == "peers":
        c = node.connect()
        rows = c.execute(
            "select peer_node_id,direction,object_type,status,"
            "written,conflict,rejected,ended_at from sync_runs "
            "order by id desc limit 20").fetchall()
        c.close()
        for r in rows:
            print(dict(r))
    elif args.sub == "sync":
        node.sync_from(args.path, args.obj)
    elif args.sub == "export":
        b = node.export_bundle(args.obj, cursor=args.cursor)
        import json
        with open(args.path, "w", encoding="utf-8") as f:
            json.dump(b, f, ensure_ascii=False)
        print("exported", len(b["items"]), "items to", args.path)


def _cmd_replay(args):
    from replay.engine_v2 import run as r2
    from replay.true_replay import run as r1
    engine = args.engine or "v2"
    if engine == "v1":
        print(r1(cutoff=args.cutoff))
    else:
        print(r2(cutoff=args.cutoff, sources=args.source,
                 match_ids=args.match,
                 window=(args.window[0], args.window[1]) if args.window else None))


def _cmd_backtest(args):
    from backtest.engine_v2 import run as b2
    print(b2(group_by=args.group_by))


def _cmd_quality(args):
    from quality.engine_v1 import run as dq
    print(dq())


def main():
    ap = argparse.ArgumentParser(description="BB Node V0.2 CLI")
    sub = ap.add_subparsers(dest="cmd")

    p = sub.add_parser("pipeline")
    p.add_argument("sub", choices=["run", "status"])
    p.add_argument("--source", nargs="+")
    p.add_argument("--stage", nargs="+")
    p.add_argument("--incremental", action="store_true")

    m = sub.add_parser("monitor")
    m.add_argument("sub", choices=["start", "stop", "status", "restart",
                                   "once", "add", "remove", "list"])
    m.add_argument("--interval", type=int)
    m.add_argument("--match")
    m.add_argument("--note")

    s = sub.add_parser("source")
    s.add_argument("sub", choices=["list", "status"])
    s.add_argument("name", nargs="?")

    sub.add_parser("market").add_argument("sub", choices=["list"], default="list")

    n = sub.add_parser("node")
    n.add_argument("sub", choices=["id", "status", "peers", "sync", "export"])
    n.add_argument("--obj", default="unified")
    n.add_argument("--cursor", type=int, default=0)
    n.add_argument("path", nargs="?")

    r = sub.add_parser("replay")
    r.add_argument("--engine", choices=["v1", "v2"], default="v2")
    r.add_argument("--cutoff", type=int)
    r.add_argument("--source", nargs="+")
    r.add_argument("--match", nargs="+")
    r.add_argument("--window", nargs=2, type=int)

    b = sub.add_parser("backtest")
    b.add_argument("--group-by",
                   choices=["match", "market", "source", "strategy",
                            "time", "version"],
                   default="match")

    sub.add_parser("quality").add_argument("sub", choices=["run"], default="run")

    args = ap.parse_args()
    handlers = {
        "pipeline": _cmd_pipeline,
        "monitor": _cmd_monitor,
        "source": _cmd_source,
        "market": _cmd_market,
        "node": _cmd_node,
        "replay": _cmd_replay,
        "backtest": _cmd_backtest,
        "quality": _cmd_quality,
    }
    if args.cmd not in handlers:
        ap.print_help()
        return
    handlers[args.cmd](args)


if __name__ == "__main__":
    main()
