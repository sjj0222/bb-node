"""Phase 11: 备份/恢复(规格 §15)与秘密扫描/日志轮转(规格 §13.2/13.4)。

备份流程(§15.2): run ID -> SQLite 在线一致性备份(Backup API) ->
SHA-256 校验和 -> integrity_check -> 清单(应用/迁移版本/大小/时间) ->
写临时文件后原子重命名 -> 保留策略(按天/数量), 删除仅限备份目录内
本应用前缀文件。
"""
import hashlib
import json
import os
import re
import shutil
import sqlite3
import time
import uuid

from core import env

BACKUP_PREFIX = "bbnode-backup-"


def _now():
    return int(time.time() * 1000)


def backup(source_db=None, dest_dir=None, conn=None, retention_days=None,
           max_backups=14, persist=True):
    """一致性备份并写校验和与清单。返回 run 元数据。"""
    src = source_db or env.db_path()
    dest_dir = dest_dir or os.path.join(os.path.dirname(src), "backups")
    os.makedirs(dest_dir, exist_ok=True)
    run_id = "bk_%s" % uuid.uuid4().hex[:12]
    ts = _now()
    stamp = time.strftime("%Y%m%d-%H%M%S", time.localtime(ts / 1000))
    final_path = os.path.join(
        dest_dir, "%s%s-%s.db" % (BACKUP_PREFIX, stamp, run_id[:8]))

    # 在线一致性备份到临时文件(SQLite Backup API, 允许并发写入)
    tmp_path = final_path + ".tmp"
    _backup_file(src, tmp_path, conn=conn)

    sha = _sha256(tmp_path)
    integrity = _integrity(tmp_path)

    manifest = {
        "run_id": run_id, "created_ms": ts,
        "source": src, "dest": final_path,
        "size_bytes": os.path.getsize(tmp_path),
        "sha256": sha, "integrity_check": integrity,
        "app_version": getattr(env, "pipeline_version", lambda: "?")()
        if hasattr(env, "pipeline_version") else "unknown",
        "schema_version": env.schema_version(),
        "retention_days": retention_days,
    }
    # 原子重命名, 避免半成品冒充成功备份(§15.2.6)
    os.replace(tmp_path, final_path)
    with open(final_path + ".sha256", "w") as f:
        f.write("%s  %s\n" % (sha, os.path.basename(final_path)))
    with open(final_path + ".json", "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)

    if conn is not None:
        try:
            conn.execute("""INSERT INTO backup_runs(
                run_id, dest, size_bytes, sha256, app_version,
                schema_version, status, created_at)
                VALUES(?,?,?,?,?,?,?,?)""",
                         (run_id, final_path, manifest["size_bytes"], sha,
                          manifest["app_version"],
                          manifest["schema_version"], "ok", ts))
            if persist:
                conn.commit()
        except Exception:
            pass   # 备份本体成功, 记录表缺失/失败不阻断

    prune(dest_dir, retention_days=retention_days,
          max_backups=max_backups, manifest=manifest)
    return manifest


def restore(backup_file, dest=None, force=False):
    """校验校验和与完整性后恢复(§15.2.3/15.2.4)。"""
    backup_file = os.path.abspath(backup_file)
    if not os.path.exists(backup_file):
        raise FileNotFoundError(backup_file)
    sha_file = backup_file + ".sha256"
    if os.path.exists(sha_file):
        with open(sha_file) as f:
            expect = f.read().split()[0]
        actual = _sha256(backup_file)
        if expect != actual:
            raise ValueError("checksum mismatch: backup 损坏或篡改")
    if _integrity(backup_file) != "ok":
        raise ValueError("integrity_check 失败: 备份不可用")

    dest = dest or env.db_path()
    if os.path.exists(dest) and not force:
        raise FileExistsError(
            "目标库已存在; 恢复会覆盖, 请显式 force=True 或先备份")
    if force and os.path.exists(dest):
        shutil.copy2(dest, dest + ".pre-restore." +
                     time.strftime("%Y%m%d-%H%M%S"))
    tmp = dest + ".restore-tmp"
    _backup_file(backup_file, tmp)
    os.replace(tmp, dest)
    return {"restored_to": dest,
            "integrity": _integrity(dest)}


def list_backups(dest_dir=None, limit=50):
    dest_dir = dest_dir or os.path.join(
        os.path.dirname(env.db_path()), "backups")
    if not os.path.isdir(dest_dir):
        return []
    items = []
    for name in os.listdir(dest_dir):
        if name.startswith(BACKUP_PREFIX) and name.endswith(".db"):
            p = os.path.join(dest_dir, name)
            manifest_path = p + ".json"
            m = None
            if os.path.exists(manifest_path):
                try:
                    with open(manifest_path, encoding="utf-8") as f:
                        m = json.load(f)
                except (ValueError, OSError):
                    pass
            items.append({"file": name, "path": p,
                          "size_bytes": os.path.getsize(p),
                          "created_ms": m["created_ms"] if m else None,
                          "sha256": m["sha256"] if m else None})
    items.sort(key=lambda x: x["created_ms"] or 0, reverse=True)
    return items[:limit]


def prune(dest_dir, retention_days=None, max_backups=14, manifest=None):
    """保留策略(§15.2.7): 按天/数量; 只删备份目录内本应用前缀文件。"""
    files = sorted(
        (f for f in os.listdir(dest_dir)
         if f.startswith(BACKUP_PREFIX) and f.endswith(".db")),
        key=lambda f: os.path.getmtime(os.path.join(dest_dir, f)))
    removed = []
    # 数量上限
    while len(files) > max_backups:
        victim = files.pop(0)
        _delete_backup(dest_dir, victim)
        removed.append(victim)
    # 按天保留: 每天保留最早一份
    if retention_days and manifest:
        keep_days = set()
        created = manifest.get("created_ms")
        if created:
            keep_days.add(time.strftime(
                "%Y%m%d", time.localtime(created / 1000)))
        for f in files:
            day = time.strftime(
                "%Y%m%d", time.localtime(
                    os.path.getmtime(os.path.join(dest_dir, f))))
            if day in keep_days:
                continue
            mtime_days = (time.time() - os.path.getmtime(
                os.path.join(dest_dir, f))) / 86400.0
            if mtime_days > retention_days:
                _delete_backup(dest_dir, f)
                files.remove(f)
                removed.append(f)
    return removed


def _delete_backup(dest_dir, name):
    for suffix in ("", ".sha256", ".json"):
        p = os.path.join(dest_dir, name + suffix)
        if os.path.exists(p):
            os.remove(p)


def _backup_file(src, dest, conn=None):
    """SQLite Backup API 在线一致性备份。"""
    s = conn if conn is not None else sqlite3.connect(src)
    d = sqlite3.connect(dest)
    try:
        s.backup(d)
    finally:
        d.close()
        if conn is None:
            s.close()


def _sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _integrity(path):
    con = sqlite3.connect(path)
    try:
        return con.execute("PRAGMA integrity_check").fetchone()[0]
    finally:
        con.close()


# ---------- 秘密扫描(§13.2) ----------

SECRET_PATTERNS = [
    (re.compile(r"(?i)\b(api[_-]?key|apikey|token|cookie|password|passwd|"
                r"secret)\s*[=:]\s*['\"]?[A-Za-z0-9_\-]{8,}['\"]?"),
     "credential-like assignment"),
    (re.compile(r"(?i)(authorization|cookie|proxy-authorization)"
                r"\s*[=:]\s*['\"][^'\"]+['\"]"), "header value"),
    (re.compile(r"\beyJ[A-Za-z0-9_\-]{20,}\.\S{10,}"), "jwt-like token"),
]

_SKIP_DIRS = {".git", "__pycache__", "node_modules", ".venv", "venv",
              "data", "run", "backups", "*.db"}
_SKIP_EXTS = {".db", ".sqlite", ".png", ".jpg", ".jpeg", ".log",
              ".lock"}


def scan_secrets(root, max_matches=100):
    """扫描仓库内疑似秘密明文(§13.2: 不能写入 Git/日志)。"""
    findings = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames
                       if d not in _SKIP_DIRS and not d.endswith(".db")]
        for name in filenames:
            path = os.path.join(dirpath, name)
            ext = os.path.splitext(name)[1].lower()
            if ext in _SKIP_EXTS or name.startswith("."):
                continue
            if os.path.getsize(path) > 2 * 1024 * 1024:
                continue
            try:
                with open(path, encoding="utf-8", errors="replace") as f:
                    for lineno, line in enumerate(f, 1):
                        for pat, label in SECRET_PATTERNS:
                            if pat.search(line):
                                findings.append({
                                    "file": os.path.relpath(path, root),
                                    "line": lineno,
                                    "pattern": label})
                                if len(findings) >= max_matches:
                                    return findings
            except (OSError, UnicodeDecodeError):
                continue
    return findings


def verify_env_hygiene(root):
    """§13.2: .env 不入库; .env.example 不含真实值。"""
    gitignore = os.path.join(root, ".gitignore")
    if not os.path.exists(gitignore):
        return {"gitignore_exists": False}
    with open(gitignore, encoding="utf-8") as f:
        gi = f.read()
    example = os.path.join(root, ".env.example")
    issues = []
    if ".env" not in gi:
        issues.append(".env 未在 .gitignore 中")
    if os.path.exists(example):
        with open(example, encoding="utf-8") as f:
            ex = f.read()
        if any(pat.search(ex) for pat, _ in SECRET_PATTERNS):
            issues.append(".env.example 疑似含真实值")
    else:
        issues.append(".env.example 缺失(可接受, 若无环境秘密)")
    return {"gitignore_has_env": ".env" in gi,
            "env_example_exists": os.path.exists(example),
            "issues": issues}


# ---------- 日志轮转(§13.4) ----------

def rotate_logs(log_dir, max_bytes=50 * 1024 * 1024, keep=5,
                prefixes=("bbnode", "stability", "collect")):
    """按大小轮转并保留 keep 份历史。"""
    rotated = []
    for name in os.listdir(log_dir):
        if not any(name.startswith(p) for p in prefixes):
            continue
        path = os.path.join(log_dir, name)
        if os.path.getsize(path) < max_bytes:
            continue
        base, ext = os.path.splitext(name)
        for i in range(keep, 0, -1):
            src = "%s.%d%s" % (base, i, ext) if i > 0 else path
            dst = "%s.%d%s" % (base, i + 1, ext)
            src_p, dst_p = os.path.join(log_dir, src), os.path.join(
                log_dir, dst)
            if os.path.exists(src_p):
                os.replace(src_p, dst_p)
        os.replace(path, os.path.join(
            log_dir, "%s.1%s" % (base, ext)))
        rotated.append(name)
        # 清理超保留数量
        for i in range(keep + 1, keep + 20):
            p = os.path.join(log_dir, "%s.%d%s" % (base, i, ext))
            if os.path.exists(p):
                os.remove(p)
    return rotated
