"""V0.2 测试矩阵 5: Strategy/Decision Plugin(规则 72)。

覆盖: 插件注册/加载/替换不修改 Core、插件 A/B 独立、Core 与 Plugin 解耦。
"""
import pytest

from strategies import engine_v1 as strat_engine
from decisions import engine_v1 as dec_engine
from strategies.plugin import (StrategyPlugin, register as reg_strat,
                               active_plugins as strat_active,
                               _REGISTRY as STRAT_REG)
from decisions.plugin import (DecisionPlugin, register as reg_dec,
                              active_plugins as dec_active,
                              _REGISTRY as DEC_REG)


class PluginA(StrategyPlugin):
    plugin_id = "test_strat_a"
    version = "1.0"
    name = "Test A"

    def evaluate(self, group):
        if any(r["signal_type"] == "TEST_SIG" for r in group):
            return {"strategy_name": "TEST_STRAT_A", "status": "TRIGGERED",
                    "evidence": {"signals": [{"signal_id": r["id"]}
                                             for r in group]}}
        return None


class PluginB(StrategyPlugin):
    plugin_id = "test_strat_b"
    version = "1.0"
    name = "Test B"

    def evaluate(self, group):
        if len(group) >= 2:
            return {"strategy_name": "TEST_STRAT_B", "status": "TRIGGERED",
                    "evidence": {"signals": []}}
        return None


def test_plugin_register_isolated(db):
    reg_strat(PluginA())
    reg_strat(PluginB())
    assert STRAT_REG["test_strat_a"].plugin_id == "test_strat_a"
    assert STRAT_REG["test_strat_b"].plugin_id == "test_strat_b"


def test_plugin_active_filter(db):
    """config strategy.active_plugins=['ah_multi_level_water'] -> 测试插件不激活。"""
    # 先显式加载默认插件(保证注册), 再注册测试插件
    import strategies.plugins.ah_multi_level_water  # noqa: F401
    reg_strat(PluginA())
    reg_strat(PluginB())
    active = [p.plugin_id for p in strat_active()]
    assert "ah_multi_level_water" in active
    assert "test_strat_a" not in active


def test_strategy_engine_runs_with_plugins(db):
    """引擎调度插件: 构造 signals -> TRIGGERED 策略落库。"""
    import time
    c = db
    now = int(time.time() * 1000)
    c.execute("""insert into signals_v1(
        canonical_match_id,source,market_type,period,old_time,new_time,
        signal_type,strength,feature_id,pipeline_version,engine_version,
        feature_json,signal_hash,created_at)
        values(?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        ("cmP", "bb", "asian_handicap", "full_time", now - 1000, now,
         "TEST_SIG", 0.9, 1, "0.2.0", "v1", "{}", "h1", now))
    c.commit()

    # 把测试插件临时加入激活集: 直接调用引擎内部(通过 monkeypatch config)
    saved = __import__("core.env", fromlist=["get"]).get(
        "strategy.active_plugins")
    import core.env as env
    env_cfg_backup = None
    try:
        # 让 active_plugins 返回全部(含测试插件)
        import strategies.plugin as sp
        orig = sp.active_plugins
        sp.active_plugins = lambda: [PluginA(), PluginB()]
        try:
            strat_engine.run(db=db)
        finally:
            sp.active_plugins = orig
        c = db
        rows = c.execute(
            "select strategy_name,status from strategies_v1").fetchall()
        c.close()
        assert any(r[0] == "TEST_STRAT_A" and r[1] == "TRIGGERED"
                   for r in rows)
    finally:
        pass


def test_decision_plugin_isolated(db):
    class MyDec(DecisionPlugin):
        plugin_id = "test_dec"
        version = "1.0"
        name = "Test Dec"

        def evaluate(self, row):
            if row["status"] == "TRIGGERED":
                return {"status": "CANDIDATE", "candidate": 1}
            return None

    reg_dec(MyDec())
    assert DEC_REG["test_dec"].plugin_id == "test_dec"


def test_decision_engine_with_plugin(db):
    """决策引擎调度插件: TRIGGERED 策略 -> CANDIDATE 决策落库。"""
    import sqlite3
    import time
    c = db
    now = int(time.time() * 1000)
    c.execute("""insert into strategies_v1(
        canonical_match_id,source,market_type,period,old_time,new_time,
        strategy_name,status,direction,selection,bet,signal_id,
        pipeline_version,engine_version,signals_json,strategy_hash,created_at)
        values(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        ("cmD", "bb", "asian_handicap", "full_time", now - 1000, now,
         "TEST_STRAT_A", "TRIGGERED", None, None, 0, 1,
         "0.2.0", "v1", "[]", "hD", now))
    c.commit()
    dec_engine.run(db=db)
    c = db
    rows = c.execute(
        "select status,candidate from decisions_v1").fetchall()
    c.close()
    assert any(r[0] == "CANDIDATE" and r[1] == 1 for r in rows)


def test_core_does_not_import_side_effect():
    """规则 46: import 模块不得执行 Pipeline/写库。"""
    import subprocess
    out = subprocess.run(
        ["python3", "-c",
         "import strategies.engine_v1, decisions.engine_v1; print('OK')"],
        capture_output=True, text=True, cwd=".")
    assert out.returncode == 0 and "OK" in out.stdout
