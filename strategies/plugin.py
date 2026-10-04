"""Strategy Plugin 框架(V0.2 P0-6, 规则 32/33/35/72)。

Strategy Engine 只负责: 分组 signals + 调度插件 + 持久化。
规则逻辑在独立 Plugin 中, 可在不修改 Core 的情况下替换/增加(规则 72)。
禁止把投资模型 V2.2 写进 Core(规则 35)。
"""
import importlib
import pkgutil
import sqlite3
from core import env

DB = env.db_path()


class StrategyPlugin:
    """Strategy 插件基类。evaluate 返回 dict 或 None。"""

    plugin_id = "base"
    version = "1.0"
    name = "Base Strategy"

    def evaluate(self, group):
        """group: 同一 (canonical, source, market_type, period, old_time, new_time)
        的 signals 列表(SQLite Row)。

        返回: {
          "strategy_name": str,
          "status": "TRIGGERED",
          "direction": None, "selection": None, "bet": 0,
          "evidence": {...},
        } 或 None(不触发)。
        """
        return None


_REGISTRY = {}


def register(plugin):
    assert isinstance(plugin, StrategyPlugin)
    _REGISTRY[plugin.plugin_id] = plugin
    _persist_plugin(plugin.plugin_id, plugin.version, plugin.name)
    return plugin


def _persist_plugin(plugin_id, version, name):
    c = sqlite3.connect(DB)
    c.execute("""insert or ignore into strategy_plugins(
        plugin_id,version,name,active,registered_at)
        values(?,?,?,1,?)""",
        (plugin_id, version, name, int(__import__("time").time() * 1000)))
    c.commit()
    c.close()


def load_plugins():
    """自动发现 strategies/plugins/ 下模块并注册。"""
    pkg = importlib.import_module("strategies.plugins")
    for mod in pkgutil.iter_modules(pkg.__path__):
        m = importlib.import_module("strategies.plugins.%s" % mod.name)
        for attr in dir(m):
            obj = getattr(m, attr)
            if isinstance(obj, type) and issubclass(obj, StrategyPlugin) \
                    and obj is not StrategyPlugin:
                register(obj())
    return list(_REGISTRY.values())


def active_plugins():
    """当前激活插件(按 config strategy.active_plugins 过滤, 默认全部)。"""
    if not _REGISTRY:
        load_plugins()
    cfg = env.get("strategy.active_plugins") or []
    if not cfg:
        return list(_REGISTRY.values())
    return [p for pid, p in _REGISTRY.items() if pid in cfg]


def get(plugin_id):
    return _REGISTRY.get(plugin_id)
