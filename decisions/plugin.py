"""Decision Plugin 框架(V0.2 P0-6, 规则 34/35)。

Decision Engine 只负责: 调度插件 + 持久化。
插件输出结构化结果(CANDIDATE 等), Core 不做投资判断(规则 13/35)。
"""
import importlib
import pkgutil
import sqlite3
from core import env

DB = env.db_path()


class DecisionPlugin:
    """Decision 插件基类。evaluate 返回 dict 或 None。"""

    plugin_id = "base"
    version = "1.0"
    name = "Base Decision"

    def evaluate(self, strategy_row):
        """strategy_row: 一条 TRIGGERED 的 strategies_v1 记录(SQLite Row)。

        返回: {
          "status": "CANDIDATE",
          "candidate": 1,
          "direction": None, "selection": None,
          "evidence": {...},
        } 或 None。
        """
        return None


_REGISTRY = {}


def register(plugin):
    assert isinstance(plugin, DecisionPlugin)
    _REGISTRY[plugin.plugin_id] = plugin
    _persist(plugin.plugin_id, plugin.version, plugin.name)
    return plugin


def _persist(plugin_id, version, name):
    c = sqlite3.connect(DB)
    c.execute("""insert or ignore into decision_plugins(
        plugin_id,version,name,active,registered_at)
        values(?,?,?,1,?)""",
        (plugin_id, version, name, int(__import__("time").time() * 1000)))
    c.commit()
    c.close()


def load_plugins():
    pkg = importlib.import_module("decisions.plugins")
    for mod in pkgutil.iter_modules(pkg.__path__):
        m = importlib.import_module("decisions.plugins.%s" % mod.name)
        for attr in dir(m):
            obj = getattr(m, attr)
            if isinstance(obj, type) and issubclass(obj, DecisionPlugin) \
                    and obj is not DecisionPlugin:
                register(obj())
    return list(_REGISTRY.values())


def active_plugins():
    if not _REGISTRY:
        load_plugins()
    cfg = env.get("decision.active_plugins") or []
    if not cfg:
        return list(_REGISTRY.values())
    return [p for pid, p in _REGISTRY.items() if pid in cfg]


def get(plugin_id):
    return _REGISTRY.get(plugin_id)
