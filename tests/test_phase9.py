"""Phase 11 测试: 备份/恢复/秘密扫描/日志轮转(规格 §15, §13.2/13.4)。

覆盖:
  1. 备份: 文件+校验和+清单; 完整性; 原子命名; 清单字段; 保留策略
  2. 恢复: 往返一致性; 校验和不匹配拒绝; 非 force 覆盖拒绝
  3. 秘密扫描: 发现疑似明文; env 卫生(.env/.env.example)
  4. 日志轮转: 超过大小轮转并保留历史
  5. 迁移 v10
"""
import json
import os
import sqlite3
import time

from database import db as database
from core import env
from ops import backup as bk


def _seed(db):
    db.execute("INSERT INTO matches(match_id, league, home, away, source, "
               "updated_at) VALUES('m1','L','H','A','bb',1)")
    db.commit()


# ---------- 1. 备份 ----------

def test_backup_creates_files_and_manifest(db):
    _seed(db)
    dest_dir = os.path.join(os.environ["BB_NODE_HOME"], "backups")
    m = bk.backup(conn=db, dest_dir=dest_dir)
    base = os.path.basename(m["dest"])
    assert os.path.exists(m["dest"])
    assert os.path.exists(m["dest"] + ".sha256")
    assert os.path.exists(m["dest"] + ".json")
    assert m["integrity_check"] == "ok"
    assert m["schema_version"] == env.schema_version()
    assert m["size_bytes"] > 0
    assert not m["dest"].endswith(".tmp")        # 原子命名完成
    man = json.load(open(m["dest"] + ".json", encoding="utf-8"))
    assert man["run_id"] == m["run_id"]
    # 清单与校验和一致
    with open(m["dest"] + ".sha256") as f:
        assert f.read().split()[0] == m["sha256"]


def test_backup_record_and_retention(db):
    _seed(db)
    dest_dir = os.path.join(os.environ["BB_NODE_HOME"], "backups")
    bk.backup(conn=db, dest_dir=dest_dir, max_backups=1)
    time.sleep(0.01)
    bk.backup(conn=db, dest_dir=dest_dir, max_backups=1)
    files = bk.list_backups(dest_dir=dest_dir)
    assert len(files) <= 1                        # 数量保留生效
    row = db.execute("select count(*) from backup_runs").fetchone()[0]
    assert row >= 2                               # 每次备份留痕


# ---------- 2. 恢复 ----------

def test_restore_roundtrip(db):
    _seed(db)
    dest_dir = os.path.join(os.environ["BB_NODE_HOME"], "backups")
    m = bk.backup(conn=db, dest_dir=dest_dir)
    db.execute("DELETE FROM matches")
    db.commit()
    restored = os.path.join(os.environ["BB_NODE_HOME"], "restored.db")
    res = bk.restore(m["dest"], dest=restored, force=True)
    assert res["integrity"] == "ok"
    con = sqlite3.connect(restored)
    n = con.execute("select count(*) from matches").fetchone()[0]
    con.close()
    assert n == 1                                 # 往返数据一致


def test_restore_rejects_corrupt(db):
    _seed(db)
    dest_dir = os.path.join(os.environ["BB_NODE_HOME"], "backups")
    m = bk.backup(conn=db, dest_dir=dest_dir)
    with open(m["dest"], "rb") as f:
        data = bytearray(f.read())
    data[512] ^= 0xFF                              # 翻转中部字节(库尾是全零)
    with open(m["dest"], "wb") as f:
        f.write(bytes(data))
        f.flush()
        os.fsync(f.fileno())
    try:
        bk.restore(m["dest"], dest=os.path.join(
            os.environ["BB_NODE_HOME"], "x.db"), force=True)
        assert False, "校验和不匹配应拒绝"
    except ValueError:
        pass


def test_restore_refuses_without_force(db):
    _seed(db)
    dest_dir = os.path.join(os.environ["BB_NODE_HOME"], "backups")
    m = bk.backup(conn=db, dest_dir=dest_dir)
    try:
        bk.restore(m["dest"], dest=env.db_path())  # 目标已存在且未 force
        assert False, "应拒绝覆盖"
    except FileExistsError:
        pass


# ---------- 3. 秘密扫描 ----------

def test_scan_secrets_finds_plaintext(tmp_path):
    (tmp_path / "code.py").write_text(
        "x = 'normal'\napi_key = 'sk-1234567890abcdef'\n", encoding="utf-8")
    (tmp_path / "notes.md").write_text("nothing secret here\n",
                                       encoding="utf-8")
    findings = bk.scan_secrets(str(tmp_path))
    assert any(f["file"] == "code.py" and f["pattern"].startswith(
        "credential-like") for f in findings)
    assert not any(f["file"] == "notes.md" for f in findings)


def test_env_hygiene_repo():
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    h = bk.verify_env_hygiene(root)
    assert h["gitignore_has_env"] is True         # .env 不入库(§13.2)


# ---------- 4. 日志轮转 ----------

def test_rotate_logs(tmp_path):
    for i, name in enumerate(("bbnode.log", "other.txt")):
        (tmp_path / name).write_text("x" * 3000, encoding="utf-8")
    rotated = bk.rotate_logs(str(tmp_path), max_bytes=1000, keep=3)
    assert "bbnode.log" in rotated
    assert os.path.exists(tmp_path / "bbnode.1.log")   # 轮转为历史
    assert (tmp_path / "other.txt").exists()           # 非前缀不动


# ---------- 5. 迁移 v10 ----------

def test_migrate_v10(db):
    tables = {r[0] for r in db.execute(
        "select name from sqlite_master where type='table'")}
    assert "backup_runs" in tables
    assert db.execute("PRAGMA user_version").fetchone()[0] == 11


def test_config_schema_version_is_10():
    assert env.schema_version() == 11
