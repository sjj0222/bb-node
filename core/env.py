"""BB Node 统一环境与配置入口。

路径解析优先级:
  BB_NODE_HOME env  >  ~/bb_node (历史兼容)  >  仓库根目录
数据库路径:
  BB_NODE_DB   env  >  config.json database.path (相对 home)  >  home/data/bb.db

配置分层(Phase 1, 规格 13.1):
  BB_NODE_CONFIG(基础配置文件, 默认 config/config.json)
  + BB_NODE_USER_CONFIG(用户覆盖配置, 默认 config/local.json, 已 gitignore)
  用户配置按 dict 深合并覆盖基础配置; 环境变量仍为最高优先级入口。

本模块无副作用:不建目录、不连库、不写文件。
"""
import os
import json
import hashlib

DEFAULT_CONFIG_NAME = "config/config.json"
DEFAULT_USER_CONFIG_NAME = "config/local.json"


class ConfigError(Exception):
    """配置缺失/损坏/不可解析(规格 13.1: 不再静默降级)。"""


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


def run_dir():
    """运行目录(PID/锁/状态文件, 规格 14.1)。默认 home/run。"""
    return os.path.join(base_dir(), "run")


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


def user_config_path():
    """用户覆盖配置路径;不存在时返回 None。"""
    p = os.environ.get("BB_NODE_USER_CONFIG")
    if p:
        return os.path.abspath(p)
    p = os.path.join(base_dir(), DEFAULT_USER_CONFIG_NAME)
    return p if os.path.exists(p) else None


def _read_json(path, strict=False):
    if not path:
        if strict:
            raise ConfigError("config path empty")
        return {}
    if not os.path.exists(path):
        if strict:
            raise ConfigError("config file not found: %s" % path)
        return {}
    try:
        with open(path, encoding="utf-8") as f:
            obj = json.load(f)
        if not isinstance(obj, dict):
            if strict:
                raise ConfigError("config root not a dict: %s" % path)
            return {}
        return obj
    except ConfigError:
        raise
    except Exception as e:
        if strict:
            raise ConfigError("config parse failed: %s: %r" % (path, e))
        return {}


def _deep_merge(base, override):
    """dict 深合并: override 递归覆盖 base。非 dict 值直接替换。"""
    out = dict(base)
    for k, v in override.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = v
    return out


def load_config(strict=False):
    """合并后的配置: 基础配置 < 用户覆盖配置。

    strict=True 时(启动入口/诊断): 基础配置缺失或解析失败即抛
    ConfigError(规格 13.1: 不允许同一参数在不同入口有不同解释,
    不静默降级); 用户覆盖配置缺失可接受(可选层), 但显式指定后
    解析失败同样抛错。
    """
    base = _read_json(_config_path(), strict=strict)
    user_path = user_config_path()
    if user_path:
        user = _read_json(user_path, strict=strict)
    else:
        user = {}
    if not user:
        return base
    return _deep_merge(base, user)


def ensure_config():
    """启动入口校验: 配置损坏/缺失时抛 ConfigError(不再静默降级)。

    与 schema_version() 的关系: 版本兜底永远等于代码 DDL 的真实版本
    (database/db.py SCHEMA_VERSION), 但配置本身缺失仍是明确错误。
    """
    load_config(strict=True)
    return config_summary()


def config():
    """加载合并配置; 基础文件不存在时返回空 dict。"""
    return load_config()


def get(path, default=None):
    """按 'a.b.c' 路径读取配置(合并后)。"""
    cur = load_config()
    for k in str(path).split("."):
        if not isinstance(cur, dict) or k not in cur:
            return default
        cur = cur[k]
    return cur


def schema_version():
    """配置声明的 schema 版本; 读不到时回退到代码 DDL 的真实版本。

    单一权威来源在 database/db.py 的 SCHEMA_VERSION 常量(迁移链所在),
    禁止在此处另写一个数字兜底, 否则配置缺失时会出现"静默降级建出
    缺列库"且自检全绿的问题(P0-1)。
    """
    try:
        v = get("database.schema_version", None)
        if v is not None:
            return int(v)
    except (TypeError, ValueError):
        pass
    from database.db import SCHEMA_VERSION
    return SCHEMA_VERSION


def pipeline_version():
    return str(get("pipeline.version", "0.1.0"))


def stale_after_seconds():
    try:
        return int(get("stale_after_seconds", 300))
    except (TypeError, ValueError):
        return 300


# 视为敏感、必须脱敏的配置键(规格 13.1/13.2)
_SENSITIVE_KEY_PARTS = (
    "token", "password", "passwd", "secret", "api_key", "apikey",
    "cookie", "authorization", "credential", "private_key",
)


def _is_sensitive_key(key):
    k = str(key).lower()
    return any(part in k for part in _SENSITIVE_KEY_PARTS)


def config_hash():
    """合并配置的规范哈希(规格 13.1: 配置 hash)。用于可复现运行与校验。"""
    obj = load_config()
    try:
        text = json.dumps(obj, sort_keys=True, ensure_ascii=False)
    except Exception:
        text = "{}"
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def config_summary():
    """脱敏后的配置摘要(规格 13.1): 输出结构概要, 绝不输出敏感值。

    返回 dict: 配置路径、版本、schema、来源启用状态、市场/引擎键表、
    以及敏感键的掩码(有则显示 <redacted>)。
    """
    cfg = load_config()
    masked = []
    for k in cfg.keys():
        if _is_sensitive_key(k):
            masked.append(str(k))

    def _walk(obj, prefix=""):
        out = {}
        for k, v in obj.items():
            key = prefix + str(k)
            if _is_sensitive_key(k) or _is_sensitive_key(key):
                out[k] = "<redacted>"
                if str(k) not in masked:
                    masked.append(str(k))
            elif isinstance(v, dict):
                out[k] = _walk(v, key + ".")
            elif isinstance(v, list):
                out[k] = "[list:%d]" % len(v)
            elif isinstance(v, bool):
                out[k] = v
            elif isinstance(v, (int, float)):
                out[k] = v
            else:
                s = str(v)
                out[k] = s if len(s) <= 64 else s[:61] + "..."
        return out

    summary = {
        "config_path": _config_path(),
        "user_config_path": user_config_path() or None,
        "config_hash": config_hash(),
        "config_version": cfg.get("config_version"),
        "schema_version": schema_version(),
        "pipeline_version": pipeline_version(),
        "contents": _walk(cfg),
        "sensitive_keys_masked": sorted(masked),
    }
    return summary

