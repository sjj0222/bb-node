"""Strategy Plugin: AH_MULTI_LEVEL_WATER(V0.2 插件示例)。

规则: 同一窗口内 WATER_SHIFT_STRONG + MULTI_LEVEL_SYNC 同时存在
-> AH_MULTI_LEVEL_WATER TRIGGERED(与 V0.1 行为等价, 独立插件化)。

仅组合 Signal(规则 12), 不修改 RAW。
"""
from strategies.plugin import StrategyPlugin


class AHMultiLevelWater(StrategyPlugin):
    plugin_id = "ah_multi_level_water"
    version = "1.0"
    name = "AH Multi-Level Water"

    def evaluate(self, group):
        names = {r["signal_type"] for r in group}
        if "WATER_SHIFT_STRONG" in names and "MULTI_LEVEL_SYNC" in names:
            return {
                "strategy_name": "AH_MULTI_LEVEL_WATER",
                "status": "TRIGGERED",
                "direction": None,
                "selection": None,
                "bet": 0,
                "evidence": {
                    "signals": [
                        {"signal_id": r["id"],
                         "signal_type": r["signal_type"],
                         "strength": r["strength"],
                         "feature_id": r["feature_id"]}
                        for r in group
                    ],
                },
            }
        return None
