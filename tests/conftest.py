"""pytest 测试基座。

- 顶层即设置隔离环境(BB_NODE_HOME/DB/REPLAY_DB/LOG), 业务模块 import 时即生效
- 每个测试函数使用独立临时数据库(函数级 fixture), 保证隔离与确定性
"""
import os
import sys
import tempfile

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO not in sys.path:
    sys.path.insert(0, REPO)

_TMP = tempfile.mkdtemp(prefix="bbnode_test_")
os.environ["BB_NODE_HOME"] = _TMP
os.environ["BB_NODE_DB"] = os.path.join(_TMP, "test.db")
os.environ["BB_NODE_REPLAY_DB"] = os.path.join(_TMP, "replay.db")
os.environ["BB_NODE_LOG"] = os.path.join(_TMP, "test.log")
os.environ["BB_NODE_CONFIG"] = os.path.join(REPO, "config", "config.json")


def make_dirs():
    for d in ("data/raw/bb", "data/raw/sx", "data/logs"):
        p = os.path.join(_TMP, d)
        if not os.path.exists(p):
            os.makedirs(p, exist_ok=True)


make_dirs()

import pytest  # noqa: E402

from database import db as database  # noqa: E402


@pytest.fixture()
def db():
    """每个测试独立全新数据库。"""
    database.init()
    yield database.connect()
    # 清理: 关闭连接并删除文件, 保证下一测试全新起点
    try:
        database.connect().close()
    except Exception:
        pass
    for suffix in ("", "-wal", "-shm"):
        p = os.environ["BB_NODE_DB"] + suffix
        if os.path.exists(p):
            os.remove(p)
