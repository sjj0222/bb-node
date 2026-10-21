"""BB Node Phase 1 统一 CLI(规格 1.1/12.1/14.1/14.2)。

命令:
  init
  check [--json]
  doctor [--json]
  pipeline run|status [--source bb sx] [--stage ...] [--incremental] [--json]
  monitor start|stop|status|restart|once [--interval N]
  monitor add|remove|list <canonical_match_id>
  source list|status [name]
  market list
  node id|status|peers
  p2p export <obj> <cursor> <path> | p2p sync <obj> <path>
  replay run [--cutoff MS] [--source ...] [--match ...]
  backtest run [--group-by match|market|source|strategy|time|version]
  quality run

退出码约定(Phase 1, 规格 12.1):
  0 = 成功 / 检查全部通过
  1 = 运行失败 / 检查存在 FAIL / 单实例锁被占用
  2 = 用法错误(argparse 默认)

单实例锁(规格 14.1/14.2):
  pipeline run 与 monitor start/restart 获取同名锁, 被占用时退出码 1,
  防止多进程重复执行采集/调度。

--json: 对 init/check/doctor/pipeline status 输出结构化 JSON。
"""
import sys
import argparse
import json


def _out_json(obj):
    import json
    print(json.dumps(obj, ensure_ascii=False, sort_keys=True, indent=2))


def _cmd_init(args):
    """幂等初始化: 建数据/运行目录、建表/迁移; 不破坏已有数据。"""
    import os
    from core import env, checks
    os.makedirs(env.data_dir(), exist_ok=True)
    os.makedirs(env.run_dir(), exist_ok=True)
    from database import db
    db.init()
    # 验证
    items = checks.db_check() + [checks.disk_check()]
    failed = [c for c in items if c["status"] == "FAIL"]
    result = {
        "init": "OK",
        "db_path": env.db_path(),
        "schema_version": env.schema_version(),
        "checks": items,
    }
    if args.json:
        _out_json(result)
    else:
        print("INIT OK db=%s schema_version=%s" % (env.db_path(), env.schema_version()))
        for c in items:
            print(" ", c["status"], c["name"], c["detail"])
    sys.exit(1 if failed else 0)


def _cmd_check(args):
    """只读检查: 配置/目录/磁盘/数据库完整性/来源健康。"""
    from core import checks
    items = checks.run_checks()
    failed = [c for c in items if c["status"] == "FAIL"]
    if args.json:
        _out_json({"checks": items, "result": "FAIL" if failed else "OK"})
    else:
        for c in items:
            print(c["status"].ljust(6), c["name"].ljust(22), c["detail"])
        print("CHECK:", "FAIL" if failed else "OK")
    sys.exit(1 if failed else 0)


def _cmd_doctor(args):
    """全面诊断: 环境信息 + 全部检查(只读)。"""
    from core import checks
    env_info = checks.env_info()
    items = checks.run_checks()
    failed = [c for c in items if c["status"] == "FAIL"]
    if args.json:
        _out_json({"env": env_info, "checks": items, "result": "FAIL" if failed else "OK"})
    else:
        print("== ENV ==")
        for k, v in env_info.items():
            print(" ", k, "=", v)
        print("== CHECKS ==")
        for c in items:
            print(c["status"].ljust(6), c["name"].ljust(22), c["detail"])
        print("DOCTOR:", "FAIL" if failed else "OK")
    sys.exit(1 if failed else 0)


def _status_json():
    import sqlite3
    from core import env, status as st
    con = sqlite3.connect("file:%s?mode=ro" % env.db_path(), uri=True, timeout=5)
    try:
        r = con.execute(
            "select max(received_at),count(*) from unified_snapshots"
        ).fetchone()
    finally:
        con.close()
    latest, total = r
    state = "NO_DATA"
    age_s = None
    if latest:
        import time
        age_s = round(time.time() - latest / 1000, 1)
        state = "OK" if age_s <= env.stale_after_seconds() else "STALE"
    return {
        "unified": {"latest_ms": latest, "rows": total, "age_s": age_s,
                    "state": state},
        "stages": st.get_status(),
    }


def _cmd_pipeline(args):
    from core import lock
    if args.sub == "status":
        if args.json:
            _out_json(_status_json())
        else:
            from core.status import print_status
            print_status()
        return
    h = lock.acquire("pipeline", timeout=0)
    if h is None:
        print("LOCK_BUSY pipeline: 另一个 pipeline run 正在执行", file=sys.stderr)
        sys.exit(1)
    try:
        from pipeline.orchestrator import run_pipeline
        results = run_pipeline(sources=args.source, stages=args.stage,
                               incremental=args.incremental)
    finally:
        h.release()
    ok = bool(results.get("PASS"))
    if args.json:
        _out_json(results)
    else:
        print("PIPELINE:", "PASS" if ok else "FAIL")
    sys.exit(0 if ok else 1)


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
    if args.sub in ("start", "restart"):
        from core import lock
        h = lock.acquire("monitor", timeout=0)
        if h is None:
            print("LOCK_BUSY monitor: 另一个 monitor 正在运行", file=sys.stderr)
            sys.exit(1)
        try:
            print(m.start() if args.sub == "start" else m.restart())
        finally:
            h.release()
        return
    if args.sub == "stop":
        print(m.stop())
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


def _cmd_unified(args):
    """Phase 7: Unified 查询(规格 §9.3)。"""
    from database.db import connect
    from unified import query as uq
    c = connect()
    try:
        if args.sub == "query":
            rows = uq.query_unified(
                c, match_id=args.match, league=args.league,
                source=args.source, market_type=args.market,
                period=args.period, side=args.side, line=args.line,
                min_odds=args.min_odds, max_odds=args.max_odds,
                fresh_ms=args.fresh_ms, limit=args.limit)
            _dump(rows, args)
        elif args.sub == "latest":
            _dump(uq.latest_quotes(c, match_id=args.match,
                                   source=args.source,
                                   market_type=args.market), args)
        elif args.sub == "series":
            if not args.match or not args.market:
                raise SystemExit("series 需要 --match 与 --market")
            _dump(uq.market_series(c, args.match, args.market,
                                   period=args.period), args)
        elif args.sub == "compare":
            if not args.match or not args.market:
                raise SystemExit("compare 需要 --match 与 --market")
            _dump(uq.cross_source_compare(
                c, args.match, args.market,
                period=args.period or "full_time"), args)
        elif args.sub == "plan":
            _dump(uq.plan_report(c), args)
    finally:
        c.close()


def _cmd_version(args):
    """Phase 13: 版本信息(VERSION + schema_version + git 描述)。"""
    import os as _os
    from core import env as _env
    ver = "unknown"
    vfile = _os.path.join(_os.path.dirname(_os.path.abspath(__file__)),
                          "VERSION")
    if _os.path.exists(vfile):
        with open(vfile, encoding="utf-8") as f:
            ver = f.read().strip()
    out = {"version": ver, "schema_version": _env.schema_version()}
    try:
        import subprocess
        out["git_head"] = subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=_os.path.dirname(_os.path.abspath(__file__)),
            stderr=subprocess.DEVNULL).decode().strip()
    except Exception:
        out["git_head"] = None
    _out_json(out) if getattr(args, "json", False) else print(
        "bb-node %s (schema v%s, git %s)"
        % (out["version"], out["schema_version"], out["git_head"] or "-"))


def _cmd_backup(args):
    """Phase 11: 备份/恢复/保留策略(规格 §15)。"""
    from ops import backup as bk
    from database.db import connect
    c = connect()
    try:
        if args.sub == "create":
            m = bk.backup(conn=c, dest_dir=args.dest,
                          retention_days=args.retention_days,
                          max_backups=args.max_backups)
            _out_json(m) if getattr(args, "json", False) else print(
                "backup ok: %s (%d bytes, sha256 %s, integrity %s)"
                % (m["dest"], m["size_bytes"], m["sha256"][:12],
                   m["integrity_check"]))
        elif args.sub == "list":
            rows = bk.list_backups(dest_dir=args.dest)
            _out_json(rows) if getattr(args, "json", False) else [
                print(r) for r in rows]
        elif args.sub == "restore":
            res = bk.restore(args.file, dest=args.dest, force=args.force)
            print(res)
    finally:
        c.close()


def _cmd_security(args):
    """Phase 11: 秘密扫描与日志轮转(规格 §13.2/13.4)。"""
    from ops import backup as bk
    import os
    root = args.root or os.path.dirname(os.path.abspath(__file__))
    if args.sub == "scan":
        findings = bk.scan_secrets(root, max_matches=args.max_matches)
        if getattr(args, "json", False):
            _out_json({"findings": findings,
                       "hygiene": bk.verify_env_hygiene(root)})
            return
        print("疑似秘密明文 %d 处:" % len(findings))
        for f in findings:
            print("  %s:%d  (%s)" % (f["file"], f["line"], f["pattern"]))
        print("env 卫生:", bk.verify_env_hygiene(root))
    elif args.sub == "rotate":
        from core import env as _env
        import os as _os
        log_dir = args.log_dir or _os.path.join(
            _os.path.dirname(_env.log_path()), "logs")
        rotated = bk.rotate_logs(log_dir, max_bytes=args.max_bytes,
                                 keep=args.keep)
        _out_json({"rotated": rotated}) if getattr(args, "json", False) \
            else print("rotated:", rotated)


def _dump(rows, args):
    import json as _json
    if getattr(args, "json", False):
        _out_json(rows)
        return
    if isinstance(rows, list):
        for r in rows[:50]:
            print(r)
    else:
        print(rows)


def _cmd_mapping(args):
    """Phase 5: 映射人工审批 CLI(规格 §8.3, 可审计)。"""
    from database.db import connect
    from mapping import audit as ma
    c = connect()
    try:
        if args.sub == "list":
            rows = ma.list_queue(c, decision=args.decision or "pending")
            if getattr(args, "json", False):
                _out_json(rows)
                return
            if not rows:
                print("review queue: (empty)")
                return
            for q in rows:
                cands = json.loads(q.get("candidates_json") or "[]")
                print("[%s] %s/%s %s vs %s @%s  reason=%s candidates=%s" % (
                    q["id"], q["source"], q["source_match_id"],
                    q.get("home"), q.get("away"), q.get("event_time"),
                    q.get("reason"),
                    " | ".join("%s(%.2f)" % (x["canonical_match_id"],
                                             x["confidence"])
                               for x in cands) or "(none)"))
        elif args.sub == "approve":
            out = ma.approve(c, args.id, operator=args.operator or "cli",
                             note=args.note or "", candidate_index=args.index)
            c.commit()
            if getattr(args, "json", False):
                _out_json(out)
            else:
                print("approved: %s -> %s (old=%s)" % (
                    out["source_match_id"], out["canonical_match_id"],
                    out["old_canonical_match_id"]))
        elif args.sub == "reject":
            out = ma.reject(c, args.id, operator=args.operator or "cli",
                            note=args.note or "")
            c.commit()
            if getattr(args, "json", False):
                _out_json(out)
            else:
                print("rejected: review %s" % args.id)
        elif args.sub == "defer":
            out = ma.defer(c, args.id, operator=args.operator or "cli",
                           note=args.note or "")
            c.commit()
            if getattr(args, "json", False):
                _out_json(out)
            else:
                print("deferred: review %s" % args.id)
        elif args.sub == "revoke":
            out = ma.revoke(c, args.source, args.source_match_id,
                            operator=args.operator or "cli",
                            note=args.note or "")
            c.commit()
            if getattr(args, "json", False):
                _out_json(out)
            else:
                print("revoked: %s/%s" % (args.source, args.source_match_id))
        elif args.sub == "audit":
            rows = ma.audit_log(c, source=args.source,
                                source_match_id=args.source_match_id)
            if getattr(args, "json", False):
                _out_json(rows)
                return
            if not rows:
                print("mapping audit: (empty)")
                return
            for r in rows:
                print("[%s] %s %s/%s %s -> %s by=%s note=%s" % (
                    r["id"], r["action"], r["source"],
                    r["source_match_id"], r["old_canonical_match_id"],
                    r["new_canonical_match_id"], r["operator"],
                    r.get("note") or ""))
    finally:
        c.close()


def _add_json(p):
    p.add_argument("--json", action="store_true", default=argparse.SUPPRESS)


def main():
    ap = argparse.ArgumentParser(description="BB Node Phase 1 CLI")
    ap.add_argument("--json", action="store_true", default=False,
                    help="对支持的命令输出结构化 JSON")
    sub = ap.add_subparsers(dest="cmd")

    ip = sub.add_parser("init", help="幂等初始化(建目录/建表/迁移, 不破坏数据)")
    _add_json(ip)

    cp = sub.add_parser("check", help="只读检查: 配置/磁盘/数据库完整性/来源健康")
    _add_json(cp)

    dp = sub.add_parser("doctor", help="全面诊断: 环境信息 + 全部检查(只读)")
    _add_json(dp)

    p = sub.add_parser("pipeline")
    p.add_argument("sub", choices=["run", "status"])
    p.add_argument("--source", nargs="+")
    p.add_argument("--stage", nargs="+")
    p.add_argument("--incremental", action="store_true")
    _add_json(p)

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

    vp = sub.add_parser("version", help="Phase 13: 版本信息")
    _add_json(vp)

    bp = sub.add_parser("backup", help="Phase 11: 备份/恢复(规格 §15)")
    bp.add_argument("sub", choices=["create", "list", "restore"])
    bp.add_argument("--dest")
    bp.add_argument("--retention-days", type=int, default=None)
    bp.add_argument("--max-backups", type=int, default=14)
    bp.add_argument("--file", help="restore 的备份文件路径")
    bp.add_argument("--force", action="store_true")
    _add_json(bp)

    sp = sub.add_parser("security", help="Phase 11: 秘密扫描/日志轮转(§13)")
    sp.add_argument("sub", choices=["scan", "rotate"])
    sp.add_argument("--root")
    sp.add_argument("--max-matches", type=int, default=100)
    sp.add_argument("--log-dir")
    sp.add_argument("--max-bytes", type=int, default=50 * 1024 * 1024)
    sp.add_argument("--keep", type=int, default=5)
    _add_json(sp)

    up = sub.add_parser("unified", help="Phase 7: Unified 查询(规格 §9.3)")
    up.add_argument("sub", choices=["query", "latest", "series",
                                    "compare", "plan"])
    up.add_argument("--match")
    up.add_argument("--league", type=int)
    up.add_argument("--source")
    up.add_argument("--market")
    up.add_argument("--period")
    up.add_argument("--side")
    up.add_argument("--line", type=float)
    up.add_argument("--min-odds", type=float)
    up.add_argument("--max-odds", type=float)
    up.add_argument("--fresh-ms", type=int)
    up.add_argument("--limit", type=int, default=100)
    _add_json(up)

    mp = sub.add_parser("mapping", help="Phase 5: 映射人工审批与审计(规格 §8.3)")
    mp.add_argument("sub", choices=["list", "approve", "reject", "defer",
                                    "revoke", "audit"])
    mp.add_argument("id", type=int, nargs="?",
                    help="review id (approve/reject/defer)")
    mp.add_argument("--decision", default=None, help="list 过滤: pending 等")
    mp.add_argument("--index", type=int, default=0,
                    help="approve 选定候选下标(默认 0)")
    mp.add_argument("--source")
    mp.add_argument("--source-match-id")
    mp.add_argument("--operator", default="cli")
    mp.add_argument("--note", default=None)
    _add_json(mp)

    args = ap.parse_args()
    handlers = {
        "init": _cmd_init,
        "check": _cmd_check,
        "doctor": _cmd_doctor,
        "pipeline": _cmd_pipeline,
        "monitor": _cmd_monitor,
        "source": _cmd_source,
        "market": _cmd_market,
        "node": _cmd_node,
        "replay": _cmd_replay,
        "backtest": _cmd_backtest,
        "quality": _cmd_quality,
        "version": _cmd_version,
        "unified": _cmd_unified,
        "backup": _cmd_backup,
        "security": _cmd_security,
        "mapping": _cmd_mapping,
    }
    if args.cmd not in handlers:
        ap.print_help()
        return
    handlers[args.cmd](args)


if __name__ == "__main__":
    main()
