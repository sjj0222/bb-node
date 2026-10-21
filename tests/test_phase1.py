"""Phase 1 测试: 配置分层/单实例锁/诊断检查/CLI 命令与退出码。

覆盖(规格 1.1/1.2/12.1/13.1/14.1/14.2):
  1. env: 用户配置深合并、config_hash 稳定、config_summary 脱敏
  2. lock: 获取/释放、同进程占用、死 pid stale 接管、pid 复用接管、
     命令行特征匹配(PID 复用防误杀)
  3. checks: 数据库完整时全部 OK; 缺库时显式 FAIL(不静默)
  4. init: 幂等(重复初始化不破坏数据、不产生重复表)
  5. cli: init/check/doctor/status 子进程冒烟 + 退出码; monitor LOCK_BUSY
"""
import json
import os
import subprocess
import sys
import time

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CLI = os.path.join(REPO, "cli.py")


def _run_cli(args, env):
    return subprocess.run(
        [sys.executable, CLI] + args,
        capture_output=True, text=True, timeout=60, env=env, cwd=REPO)


def _cli_env(home):
    env = dict(os.environ)
    env.update({
        "BB_NODE_HOME": str(home),
        "BB_NODE_DB": os.path.join(str(home), "data", "bb.db"),
        "BB_NODE_LOG": os.path.join(str(home), "data", "logs", "bb-node.log"),
        "BB_NODE_CONFIG": os.path.join(REPO, "config", "config.json"),
    })
    env.pop("BB_NODE_USER_CONFIG", None)
    return env


# ---------- 1. env 配置分层 ----------

def test_env_user_config_merge(monkeypatch, tmp_path):
    base = {
        "sources": {"bb": {"enabled": True}, "sx": {"enabled": True}},
        "stale_after_seconds": 300,
        "database": {"schema_version": 3},
        "pipeline": {"version": "0.2.0"},
    }
    user = {"sources": {"bb": {"enabled": False}}, "stale_after_seconds": 60}
    base_path = tmp_path / "base.json"
    user_path = tmp_path / "local.json"
    base_path.write_text(json.dumps(base), encoding="utf-8")
    user_path.write_text(json.dumps(user), encoding="utf-8")
    monkeypatch.setenv("BB_NODE_CONFIG", str(base_path))
    monkeypatch.setenv("BB_NODE_USER_CONFIG", str(user_path))

    from core import env
    cfg = env.load_config()
    assert cfg["sources"]["bb"]["enabled"] is False   # 用户层覆盖
    assert cfg["sources"]["sx"]["enabled"] is True    # 未覆盖保留
    assert cfg["stale_after_seconds"] == 60
    assert cfg["database"]["schema_version"] == 3     # 深层字段保留
    assert env.get("sources.bb.enabled") is False     # get() 走合并后配置


def test_env_config_hash_stable(monkeypatch, tmp_path):
    base = {"a": 1, "b": {"c": [1, 2]}, "nested": {"d": "x"}}
    p = tmp_path / "base.json"
    p.write_text(json.dumps(base), encoding="utf-8")
    monkeypatch.setenv("BB_NODE_CONFIG", str(p))
    monkeypatch.delenv("BB_NODE_USER_CONFIG", raising=False)

    from core import env
    h1 = env.config_hash()
    h2 = env.config_hash()
    assert h1 == h2
    assert len(h1) == 64


def test_env_config_summary_redacts_secrets(monkeypatch, tmp_path):
    base = {"pipeline": {"version": "0.2.0"},
            "api": {"base_url": "https://api.example.com"},
            "password": "supersecret123",
            "nested": {"token": "tok_abc"}}
    p = tmp_path / "base.json"
    p.write_text(json.dumps(base), encoding="utf-8")
    monkeypatch.setenv("BB_NODE_CONFIG", str(p))
    monkeypatch.delenv("BB_NODE_USER_CONFIG", raising=False)

    from core import env
    s = env.config_summary()
    assert "supersecret123" not in json.dumps(s)
    assert "tok_abc" not in json.dumps(s)
    assert s["contents"]["password"] == "<redacted>"
    assert s["contents"]["nested"]["token"] == "<redacted>"
    assert "password" in s["sensitive_keys_masked"]
    assert "token" in s["sensitive_keys_masked"]


# ---------- 2. 单实例锁 ----------

def test_lock_acquire_release(db):
    from core import lock
    h = lock.acquire("testlock", timeout=0, markers=("python",))
    assert h is not None
    path = lock._lock_path("testlock")
    assert os.path.exists(path)
    with open(path, encoding="utf-8") as f:
        content = json.load(f)
    assert content["pid"] == os.getpid()
    assert content["name"] == "testlock"
    assert "token" in content and content["token"]
    h.release()
    assert not os.path.exists(path)
    h3 = lock.acquire("testlock", timeout=0, markers=("python",))
    assert h3 is not None
    h3.release()


def test_lock_busy_same_process(db):
    from core import lock
    h = lock.acquire("busy", timeout=0, markers=("python",))
    assert h is not None
    h2 = lock.acquire("busy", timeout=0, markers=("python",))
    assert h2 is None            # 真占用 -> 拒绝
    h.release()
    h3 = lock.acquire("busy", timeout=0, markers=("python",))
    assert h3 is not None        # 释放后可再获取
    h3.release()


def test_lock_stale_dead_pid(db):
    from core import lock
    p = subprocess.Popen([sys.executable, "-c", "pass"])
    p.wait()
    dead_pid = p.pid
    path = lock._lock_path("stale_dead")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"pid": dead_pid, "token": "old", "name": "stale_dead"}, f)
    h = lock.acquire("stale_dead", timeout=0)
    assert h is not None          # pid 不存在 -> stale -> 接管
    h.release()
    assert not os.path.exists(path)


def test_lock_stale_pid_reuse(db):
    from core import lock
    # 用自身存活 pid 但 cmdline 不含本程序标记 -> 视为 PID 被复用 -> 接管
    path = lock._lock_path("stale_reuse")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"pid": os.getpid(), "token": "old", "name": "stale_reuse"}, f)
    h = lock.acquire("stale_reuse", timeout=0,
                     markers=("__definitely_not_a_marker__",))
    assert h is not None
    h.release()


def test_lock_true_busy_foreign_process(db, monkeypatch, tmp_path):
    """外部进程持有锁(cli.py 特征在 cmdline) -> 真占用 -> acquire 返回 None。"""
    from core import lock
    home = tmp_path / "home"
    monkeypatch.setenv("BB_NODE_HOME", str(home))
    helper = os.path.join(REPO, "tests", "_lock_helper.py")
    env = _cli_env(home)
    proc = subprocess.Popen([sys.executable, helper, "foreign"],
                            env=env, cwd=REPO)
    try:
        path = os.path.join(str(home), "run", "foreign.lock")
        deadline = time.time() + 10
        while time.time() < deadline:
            if os.path.exists(path):
                break
            time.sleep(0.1)
        assert os.path.exists(path), "helper 未创建锁文件"
        # 默认 markers 应命中 helper 的 cmdline(路径含 bb-node) -> 真占用
        h = lock.acquire("foreign", timeout=0)
        assert h is None
    finally:
        proc.terminate()
        proc.wait(timeout=5)


# ---------- 3. 诊断检查 ----------

def test_checks_ok_with_init_db(db):
    from core import checks
    items = checks.run_checks()
    by_name = {c["name"]: c for c in items}
    assert by_name["config_parse"]["status"] == "OK"
    assert by_name["base_dir_writable"]["status"] == "OK"
    assert by_name["db_exists"]["status"] == "OK"
    assert by_name["db_integrity"]["status"] == "OK"
    assert by_name["db_journal"]["status"] == "OK"
    assert by_name["db_schema_version"]["status"] == "OK"
    assert by_name["db_writable"]["status"] == "OK"
    assert by_name["disk"]["status"] in ("OK", "WARN")
    assert not [c for c in items if c["status"] == "FAIL"]


def test_checks_missing_db_is_explicit_fail(db, monkeypatch, tmp_path):
    monkeypatch.setenv("BB_NODE_DB", str(tmp_path / "nope.db"))
    from core import checks
    items = checks.run_checks()
    by_name = {c["name"]: c for c in items}
    assert by_name["db_exists"]["status"] == "FAIL"
    assert by_name["db_integrity"]["status"] == "NOT_RUN"


# ---------- 4. init 幂等 ----------

def test_init_idempotent(db):
    from database import db as database
    database.init()  # 第二次初始化
    con = database.connect()
    integrity = con.execute("pragma integrity_check").fetchone()[0]
    tables = {r[0] for r in con.execute(
        "select name from sqlite_master where type='table'")}
    n_unified = con.execute("select count(*) from unified_snapshots").fetchone()[0]
    n_events = con.execute("select count(*) from events_v3").fetchone()[0]
    con.close()
    assert integrity == "ok"
    for t in ("unified_snapshots", "events_v3", "features_v2", "signals_v1",
              "strategies_v1", "decisions_v1", "pipeline_runs",
              "source_health", "stability_runs"):
        assert t in tables
    # 重复初始化不产生重复数据
    assert n_unified == 0
    assert n_events == 0


# ---------- 5. CLI 冒烟与退出码 ----------

def test_cli_init_check_doctor_status(tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    env = _cli_env(home)

    r = _run_cli(["init"], env)
    assert r.returncode == 0, r.stderr
    assert "INIT OK" in r.stdout
    # 重复 init 幂等, 仍退出 0
    r2 = _run_cli(["init"], env)
    assert r2.returncode == 0, r2.stderr

    r = _run_cli(["check"], env)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "CHECK: OK" in r.stdout

    r = _run_cli(["doctor", "--json"], env)
    assert r.returncode == 0, r.stderr
    obj = json.loads(r.stdout)
    assert "env" in obj and "checks" in obj
    assert obj["result"] == "OK"

    r = _run_cli(["pipeline", "status", "--json"], env)
    assert r.returncode == 0, r.stderr
    obj = json.loads(r.stdout)
    assert "unified" in obj and "stages" in obj


def test_cli_check_missing_config_fails(tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    env = _cli_env(home)
    env["BB_NODE_CONFIG"] = str(home / "no_such_config.json")
    r = _run_cli(["check"], env)
    assert r.returncode == 1
    assert "config_parse" in r.stdout
    assert "CHECK: FAIL" in r.stdout


def test_cli_monitor_lock_busy(tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    env = _cli_env(home)
    helper = os.path.join(REPO, "tests", "_lock_helper.py")
    proc = subprocess.Popen([sys.executable, helper, "monitor"],
                            env=env, cwd=REPO)
    try:
        lock_path = os.path.join(str(home), "run", "monitor.lock")
        deadline = time.time() + 10
        while time.time() < deadline:
            if os.path.exists(lock_path):
                break
            time.sleep(0.1)
        assert os.path.exists(lock_path), "helper 未持有 monitor 锁"
        r = _run_cli(["monitor", "start"], env)
        assert r.returncode == 1
        assert "LOCK_BUSY monitor" in r.stderr
    finally:
        proc.terminate()
        proc.wait(timeout=5)
