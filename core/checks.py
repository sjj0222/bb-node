"""Phase 1 启动/运行诊断检查(规格 1.2/14.1)。

只读模块: 不建表、不写库、不修改任何数据。供 `cli.py check / doctor`
与未来启动流程复用。每一项返回结构化 {name, status, detail}。

status 取值: OK / WARN / FAIL / NOT_RUN
"""
import os
import platform
import sqlite3
import sys
import time

from core import env


def _now_ms():
    return int(time.time() * 1000)


def _fmt_bytes(n):
    if n is None:
        return "?"
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024 or unit == "TB":
            return "%.1f%s" % (n, unit)
        n /= 1024.0
    return "%.1fTB" % n


def _db_ro_connect(path):
    """只读连接数据库(不触发写)。uri 模式。"""
    return sqlite3.connect("file:%s?mode=ro" % path, uri=True, timeout=5)


def env_info():
    cfg = env.load_config()
    return {
        "generated_at": _now_ms(),
        "host": platform.node(),
        "python_version": platform.python_version(),
        "platform": sys.platform,
        "base_dir": env.base_dir(),
        "run_dir": env.run_dir(),
        "data_dir": env.data_dir(),
        "db_path": env.db_path(),
        "log_path": env.log_path(),
        "config_path": env._config_path(),
        "user_config_path": env.user_config_path(),
        "config_hash": env.config_hash(),
        "config_version": cfg.get("config_version"),
        "schema_version_config": env.schema_version(),
        "pipeline_version": env.pipeline_version(),
    }


def disk_check():
    """数据目录所在文件系统的可用空间。"""
    d = env.data_dir()
    thresholds = {
        "warn_bytes": env.get("database.disk_warn_mb", 1024) * 1024 * 1024,
        "fail_bytes": env.get("database.disk_fail_mb", 200) * 1024 * 1024,
    }
    try:
        st = os.statvfs(d)
        free = st.f_bavail * st.f_frsize
    except OSError as e:
        return {"name": "disk", "status": "FAIL", "detail": "无法读取磁盘空间: %s" % e}
    if free <= thresholds["fail_bytes"]:
        status, tail = "FAIL", "低于失败阈值 %s" % _fmt_bytes(thresholds["fail_bytes"])
    elif free <= thresholds["warn_bytes"]:
        status, tail = "WARN", "低于告警阈值 %s" % _fmt_bytes(thresholds["warn_bytes"])
    else:
        status, tail = "OK", "充足"
    return {"name": "disk", "status": status,
            "detail": "free=%s (%s), 阈值 warn<=%s fail<=%s" % (
                _fmt_bytes(free), tail,
                _fmt_bytes(thresholds["warn_bytes"]),
                _fmt_bytes(thresholds["fail_bytes"]))}


def db_check():
    """数据库文件: 存在/完整性/日志模式/schema 版本一致/可写。只读。"""
    path = env.db_path()
    checks = []
    if not os.path.exists(path):
        checks.append({"name": "db_exists", "status": "FAIL",
                       "detail": "数据库文件不存在: %s" % path})
        checks.append({"name": "db_integrity", "status": "NOT_RUN",
                       "detail": "文件不存在, 跳过"})
        checks.append({"name": "db_schema_version", "status": "NOT_RUN",
                       "detail": "文件不存在, 跳过"})
    else:
        checks.append({"name": "db_exists", "status": "OK", "detail": path})
        try:
            con = _db_ro_connect(path)
            try:
                integrity = con.execute("PRAGMA integrity_check").fetchone()[0]
                journal = con.execute("PRAGMA journal_mode").fetchone()[0]
                try:
                    uv = con.execute("PRAGMA user_version").fetchone()[0]
                except Exception:
                    uv = None
                checks.append({"name": "db_integrity",
                               "status": "OK" if integrity == "ok" else "FAIL",
                               "detail": "integrity_check=%s" % integrity})
                checks.append({"name": "db_journal", "status": "OK", "detail": journal})
                want = env.schema_version()
                checks.append({
                    "name": "db_schema_version",
                    "status": "OK" if uv == want else "FAIL",
                    "detail": "user_version=%s vs config schema_version=%s" % (uv, want)})
            finally:
                con.close()
        except Exception as e:
            checks.append({"name": "db_integrity", "status": "FAIL",
                           "detail": "只读连接失败: %s" % e})
        checks.append({"name": "db_writable",
                       "status": "OK" if os.access(path, os.W_OK) else "FAIL",
                       "detail": "writable=%s" % os.access(path, os.W_OK)})
    return checks


def source_check():
    """来源配置与健康记录。"""
    cfg = env.load_config()
    sources = cfg.get("sources") or {}
    items = []
    for name, s in sources.items():
        enabled = bool(s.get("enabled", True))
        items.append({"name": "source_%s" % name,
                      "status": "OK" if enabled else "WARN",
                      "detail": "enabled=%s" % enabled})
    # 读取 source_health(只读; 库可能不存在则跳过)
    try:
        con = _db_ro_connect(env.db_path())
        try:
            rows = con.execute(
                "SELECT source, status, last_success, error_count FROM source_health"
            ).fetchall()
            stale_after = env.stale_after_seconds()
            now = _now_ms()
            for source, status, last_success, errors in rows:
                age = None
                if last_success:
                    age = (now - last_success) / 1000.0
                if status == "UP" and (age is None or age <= stale_after * 5):
                    st = "OK"
                    tail = "last_success_age=%ss" % ("?" if age is None else round(age))
                elif status == "UP":
                    st = "WARN"
                    tail = "数据偏旧 age=%ss (stale_after=%ss)" % (
                        round(age or 0), stale_after)
                else:
                    st = "FAIL"
                    tail = "status=%s errors=%s" % (status, errors)
                items.append({"name": "health_%s" % source, "status": st,
                              "detail": tail})
        except sqlite3.Error as e:
            items.append({"name": "source_health", "status": "NOT_RUN",
                          "detail": "读取失败: %s" % e})
        finally:
            con.close()
    except sqlite3.Error:
        items.append({"name": "source_health", "status": "NOT_RUN",
                      "detail": "数据库不可读, 跳过"})
    return items


def pipeline_check():
    """最近一次 pipeline run 的状态摘要(只读)。

    状态枚举单一来源 = core/status.py 常量(实际写入值是 OK/RUNNING/
    ERROR, 不是 success/running——P3-12)。
    """
    from core.status import OK, RUNNING, NO_RUN
    FAIL = "FAIL"
    try:
        con = _db_ro_connect(env.db_path())
        try:
            row = con.execute(
                "SELECT run_id, stage, status, start_time, end_time, message "
                "FROM pipeline_runs ORDER BY start_time DESC LIMIT 1"
            ).fetchone()
            if not row:
                return [{"name": "pipeline_last", "status": "NOT_RUN",
                         "detail": "无 pipeline 记录"}]
            run_id, stage, status, started, finished, error = row
            # checks 枚举: OK/WARN/FAIL/NOT_RUN; ERROR 与未知一律 FAIL
            st = (OK if status == OK else RUNNING if status == RUNNING
                  else FAIL)
            return [{"name": "pipeline_last", "status": st,
                     "detail": "run_id=%s stage=%s status=%s error=%s" % (
                         run_id, stage, status, error)}]
        finally:
            con.close()
    except sqlite3.Error as e:
        return [{"name": "pipeline_last", "status": "NOT_RUN", "detail": "%s" % e}]


def run_checks():
    """运行全部检查, 返回 [(name, status, detail), ...]。"""
    out = []
    try:
        env.load_config(strict=True)
        out.append({"name": "config_parse", "status": "OK",
                    "detail": "config_hash=%s" % env.config_hash()[:16]})
    except env.ConfigError as e:
        out.append({"name": "config_parse", "status": "FAIL",
                    "detail": str(e)})
    out.append({"name": "base_dir_writable",
                "status": "OK" if os.access(env.base_dir(), os.W_OK) else "FAIL",
                "detail": env.base_dir()})
    out.append(disk_check())
    out.extend(db_check())
    out.extend(source_check())
    out.extend(pipeline_check())
    return out


def doctor():
    """汇总环境信息 + 全部检查。"""
    return {
        "env": env_info(),
        "checks": run_checks(),
        "check_count": None,  # 由 CLI 计算
    }
