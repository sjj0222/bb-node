"""Decision Plugin: CANDIDATE(V0.2 插件示例)。

TRIGGERED 策略 -> CANDIDATE(结构化候选, 不自动下注, 规则 0/13)。
"""
from decisions.plugin import DecisionPlugin


class Candidate(DecisionPlugin):
    plugin_id = "candidate"
    version = "1.0"
    name = "Candidate Decision"

    def evaluate(self, strategy_row):
        if strategy_row["status"] == "TRIGGERED":
            return {
                "status": "CANDIDATE",
                "candidate": 1,
                "direction": None,
                "selection": None,
                "evidence": {
                    "strategy": strategy_row["strategy_name"],
                    "strategy_id": strategy_row["id"],
                    "signals_json": strategy_row["signals_json"],
                },
            }
        return None
