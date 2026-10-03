"""BB Node 统一环境与配置入口。

路径解析优先级:
  BB_NODE_HOME env  >  ~/bb_node (历史兼容)  >  仓库根目录
数据库路径:
  BB_NODE_DB   env  >  config.json database.path (相对 home)  >  home/data/bb.db

本模块无副作用:不建目录、不连库、不写文件。
"""
import os
import json

DEFAULT_CONFIG_NAME = "config/config.json"


def base_dir():
    p = os.environ.get("BB_NODE_HOME")
    if p:
        return os.path.abspath(p)
    default = os.path.expanduser("~/bb_node")
    if os.path.isdir(default):
        return default
    # fallback: 本仓库根目录 (core/env.py 的上级)
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def data_dir():
    d = os.path.join(base_dir(), "data")
    return d


def db_path():
    p = os.environ.get("BB_NODE_DB")
    if p:
        return os.path.abspath(p)
    cfg = load_config()
    rel = (cfg.get("database") or {}).get("path")
    if rel:
        return os.path.join(base_dir(), rel)
    return os.path.join(data_dir(), "bb.db")


def log_path():
    p = os.environ.get("BB_NODE_LOG")
    if p:
        return os.path.abspath(p)
    return os.path.join(data_dir(), "logs", "bb-node.log")


def raw_dir(source):
    return os.path.join(data_dir(), "raw", source)


def _config_path():
    p = os.environ.get("BB_NODE_CONFIG")
    if p:
        return os.path.abspath(p)
    return os.path.join(base_dir(), DEFAULT_CONFIG_NAME)


def load_config():
    path = _config_path()
    if not os.path.exists(path):
        return {}
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def config():
    """加载配置;BB_NODE_CONFIG 指向的文件不存在时返回空 dict。"""
    return load_config()


def get(path, default=None):
    """按 'a.b.c' 路径读取配置。"""
    cur = load_config()
    for k in str(path).split("."):
        if not isinstance(cur, dict) or k not in cur:
            return default
        cur = cur[k]
    return cur


def schema_version():
    try:
        return int(get("database.schema_version", 2))
    except (TypeError, ValueError):
        return 2


def pipeline_version():
    return str(get("pipeline.version", "0.1.0"))


def stale_after_seconds():
    try:
        return int(get("stale_after_seconds", 300))
    except (TypeError, ValueError):
        return 300
