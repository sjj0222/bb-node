"""Monitor(V0.2 P0-1, 规则 5/6/7/8/9)。

- Manual Mode: run_once()
- Daemon Mode: start() 后台循环 + stop()/status()/restart()
- 状态机: STOPPED / STARTING / RUNNING / DEGRADED / ERROR / STOPPING(规则 6.1)
- Source 故障隔离: 一个 Source DOWN -> DEGRADED, 其余 Source 继续(规则 6.2)
- 选定比赛: watchlist(add/remove/list/status) + 专项输出(规则 7)
- 输出: 每轮事件/信号/策略/决策变化 + 结构化 Alert(规则 8/9)
"""
import time
import sqlite3
import threading
from core import env
from core.log import log_event, new_trace_id
from monitor import alert as alert_mod
from monitor import watchlist

DB = env.db_path()

STOPPED = "STOPPED"
STARTING = "STARTING"
RUNNING = "RUNNING"
DEGRADED = "DEGRADED"
ERROR = "ERROR"
STOPPING = "STOPPING"


class Monitor:
    def __init__(self, interval_seconds=None, watchlist_only=None,
                 run_incremental=None):
        cfg = env.get("monitor") or {}
        self.interval = interval_seconds or cfg.get("interval_seconds", 300)
        self.watchlist_only = (
            watchlist_only if watchlist_only is not None
            else cfg.get("watchlist_only", False))
        self.run_incremental = (
            run_incremental if run_incremental is not None
            else cfg.get("run_incremental", True))
        self.state = STOPPED
        self._thread = None
        self._stop_evt = threading.Event()
        self.monitor_run_id = None
        self.rounds = 0
        self.alerts = 0
        self.errors = 0
        self.last_round_at = None

    # ---------- 状态 ----------
    def status(self):
        return {
            "state": self.state,
            "monitor_run_id": self.monitor_run_id,
            "interval_seconds": self.interval,
            "rounds": self.rounds,
            "alerts": self.alerts,
            "errors": self.errors,
            "last_round_at": self.last_round_at,
            "watchlist_only": self.watchlist_only,
            "incremental": self.run_incremental,
            "watchlist": [w["canonical_match_id"]
                          for w in watchlist.list_all()],
            "open_alerts": alert_mod.open_count(),
        }

    def _persist_state(self, ended=False):
        c = sqlite3.connect(DB)
        if self.monitor_run_id is None:
            self.monitor_run_id = new_trace_id("monitor")
        c.execute("""insert into monitor_runs(
            monitor_run_id,started_at,status,interval_seconds,
            selected_only,rounds,alerts,errors,last_round_at,ended_at)
            values(?,?,?,?,?,?,?,?,?,?)""",
            (self.monitor_run_id, int(time.time() * 1000),
             self.state, self.interval, int(self.watchlist_only),
             self.rounds, self.alerts, self.errors, self.last_round_at,
             int(time.time() * 1000) if ended else None))
        c.commit()
        c.close()

    # ---------- 一轮 ----------
    def _run_round(self):
        t0 = time.time()
        from pipeline.orchestrator import run_pipeline

        try:
            monitor_run_id = self.monitor_run_id or new_trace_id("monitor")
            self.monitor_run_id = monitor_run_id
            trace_id = new_trace_id("pipeline")
            log_event("INFO", "MONITOR", "round",
                      "monitor round start (incremental=%s)" % self.run_incremental,
                      monitor_run_id)

            # 1) 采集 + 全链路
            stages = ["COLLECT", "NORMALIZE", "MAPPING", "UNIFIED", "QUALITY",
                      "EVENT", "EVENT_GROUP", "FEATURE", "SIGNAL",
                      "STRATEGY", "DECISION"]
            result = run_pipeline(stages=stages, trace_id=trace_id)
            ok = True
            if isinstance(result, dict):
                ok = result.get("PASS", True)
            if not ok:
                self.errors += 1
                self.state = DEGRADED
                alert_mod.emit("PIPELINE_ERROR",
                               "pipeline round failed", severity="ERROR",
                               monitor_run_id=monitor_run_id,
                               pipeline_run_id=trace_id)
                log_event("ERROR", "MONITOR", "round", "pipeline failed",
                          monitor_run_id)

            # 2) Source Health -> Alert
            from core import health
            for h in health.list_all():
                if h["status"] in (health.DOWN, health.NETWORK_ERROR,
                                   health.INVALID_RESPONSE):
                    alert_mod.emit(
                        "SOURCE_DOWN",
                        "source %s DOWN: %s" % (
                            h["source"], (h["last_error"] or "")[:120]),
                        severity="CRITICAL", entity=h["source"],
                        source=h["source"], monitor_run_id=monitor_run_id)
                    self.alerts += 1
                elif health.status_of(h["source"]) == health.STALE:
                    alert_mod.emit("SOURCE_STALE",
                                   "source %s STALE" % h["source"],
                                   severity="WARN", entity=h["source"],
                                   source=h["source"], monitor_run_id=monitor_run_id)
                    self.alerts += 1

            # 3) DQ Alert
            try:
                from quality.engine_v1 import run as dq_run
                dq = dq_run(pipeline_run_id=trace_id, trace_id=monitor_run_id)
                if dq and (dq["conflict"] or dq["invalid"]):
                    alert_mod.emit(
                        "DATA_QUALITY_ERROR",
                        "dq invalid=%s conflict=%s missing=%s" % (
                            dq["invalid"], dq["conflict"], dq["missing"]),
                        severity="WARN", monitor_run_id=monitor_run_id,
                        pipeline_run_id=trace_id)
                    self.alerts += 1
            except Exception as e:
                self.errors += 1
                log_event("ERROR", "QUALITY", "dq", str(e)[:200],
                          monitor_run_id)

            # 4) 选定比赛输出(规则 7/8)
            for w in watchlist.status():
                if w["signals"] or w["decisions"]:
                    alert_mod.emit(
                        "DECISION_CANDIDATE",
                        "watch %s unified=%s signals=%s decisions=%s" % (
                            w["canonical_match_id"], w["unified"],
                            w["signals"], w["decisions"]),
                        severity="INFO", entity=w["canonical_match_id"],
                        monitor_run_id=monitor_run_id)

            self.rounds += 1
            self.last_round_at = int(time.time() * 1000)
            log_event("INFO", "MONITOR", "round",
                      "round done in %.1fs ok=%s" % (time.time() - t0, ok),
                      monitor_run_id)
            return ok
        except Exception as e:
            self.errors += 1
            self.state = ERROR
            alert_mod.emit("PIPELINE_ERROR",
                           "monitor round crashed: %s" % str(e)[:200],
                           severity="CRITICAL", monitor_run_id=monitor_run_id)
            log_event("ERROR", "MONITOR", "round", str(e)[:300],
                      monitor_run_id)
            return False

    # ---------- 运行模式 ----------
    def run_once(self):
        """Manual Mode: 执行一轮即返回(单轮异常 -> ERROR, 不崩溃)。"""
        self.state = STARTING
        self._persist_state()
        self.state = RUNNING
        try:
            ok = self._run_round()
        except Exception as e:
            self.errors += 1
            self.state = ERROR
            alert_mod.emit("PIPELINE_ERROR",
                           "monitor round crashed: %s" % str(e)[:200],
                           severity="CRITICAL",
                           monitor_run_id=self.monitor_run_id)
            log_event("ERROR", "MONITOR", "round", str(e)[:300],
                      self.monitor_run_id)
            ok = False
        self.state = RUNNING if (ok and self.errors == 0) else DEGRADED
        self._persist_state(ended=True)
        return ok

    def start(self, daemon=True):
        """Daemon Mode: 后台循环。"""
        if self.state in (RUNNING, STARTING):
            return self.status()
        self.state = STARTING
        self._stop_evt.clear()
        self._persist_state()
        self.state = RUNNING
        self._thread = threading.Thread(target=self._loop, daemon=daemon)
        self._thread.start()
        log_event("INFO", "MONITOR", "monitor",
                  "monitor started interval=%s" % self.interval,
                  self.monitor_run_id)
        return self.status()

    def _loop(self):
        while not self._stop_evt.is_set():
            self._run_round()
            self._persist_state()
            self._stop_evt.wait(self.interval)

    def stop(self):
        self.state = STOPPING
        self._stop_evt.set()
        if self._thread:
            self._thread.join(timeout=self.interval + 10)
        self.state = STOPPED
        self._persist_state(ended=True)
        log_event("INFO", "MONITOR", "monitor", "monitor stopped",
                  self.monitor_run_id)
        return self.status()

    def restart(self):
        self.stop()
        self.rounds = 0
        self.errors = 0
        self.alerts = 0
        self.monitor_run_id = None
        return self.start()


def main():
    """python3 -m monitor.monitor start|stop|status|restart|once [--interval N]"""
    import sys
    cmd = sys.argv[1] if len(sys.argv) > 1 else "status"
    interval = None
    if "--interval" in sys.argv:
        interval = int(sys.argv[sys.argv.index("--interval") + 1])
    m = Monitor(interval_seconds=interval)
    if cmd == "start":
        print(m.start())
    elif cmd == "stop":
        print(m.stop())
    elif cmd == "restart":
        print(m.restart())
    elif cmd == "once":
        print("round ok:", m.run_once())
    else:
        print(m.status())


if __name__ == "__main__":
    main()
