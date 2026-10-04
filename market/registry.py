"""Market Plugin Registry(V0.2, 规则 15/16/18/19)。

核心 Pipeline 不得硬编码 if/else 无限扩展盘口类型。
通过统一 Market Handler 机制:
  Market Type -> Market Handler -> 解析/校验 -> Unified

不支持的 Market: 保留 RAW + Normalized, Mapping 状态 = UNSUPPORTED/PENDING,
绝不静默丢弃(规则 18)。
"""
from core import env

UNSUPPORTED = "UNSUPPORTED"


class MarketHandler:
    """单一市场类型的解析/校验/规范化接口。"""

    name = "base"
    requires_line = False
    supported = True

    def normalize(self, record, mtype):
        """返回 (status, line, side) 或抛 ValueError。"""
        return "MAPPED", record.line, record.side

    def __repr__(self):
        return "<MarketHandler %s supported=%s>" % (self.name, self.supported)


class AHHandler(MarketHandler):
    name = "ah"
    requires_line = True


class TotalHandler(MarketHandler):
    name = "total"
    requires_line = True


class MatchResultHandler(MarketHandler):
    """1X2 / binary / double_chance: 不需要 line。"""
    name = "1x2"
    requires_line = False


class UnsupportedHandler(MarketHandler):
    name = "unsupported"
    supported = False

    def normalize(self, record, mtype):
        return UNSUPPORTED, None, None


# market_type(语义) -> handler 名
_DEFAULT = {
    "asian_handicap": AHHandler,
    "over_under": TotalHandler,
    "total": TotalHandler,
    "corner_over_under": TotalHandler,
    "corner_total": TotalHandler,   # 角球大小球(真实数据存在, V0.1 已 MAPPED)
    "1x2": MatchResultHandler,
    "double_chance": MatchResultHandler,
    "binary": MatchResultHandler,
}


class MarketRegistry:
    def __init__(self):
        self._handlers = {}
        self._load_defaults()

    def _load_defaults(self):
        cfg = (env.get("market.handlers") or {})
        for mtype, handler_name in cfg.items():
            cls = None
            for c in (_DEFAULT.get(handler_name), _DEFAULT.get(mtype)):
                if c:
                    cls = c
                    break
            self._handlers[mtype] = (cls or UnsupportedHandler)()

    def register(self, mtype, handler):
        """插件式注册(规则 16): 外部 Market Plugin 可覆盖/新增。"""
        self._handlers[mtype] = handler

    def get(self, mtype):
        h = self._handlers.get(mtype)
        if h is None:
            h = UnsupportedHandler()
            self._handlers[mtype] = h
        return h

    def list(self):
        return {k: v.name for k, v in self._handlers.items()}


REGISTRY = MarketRegistry()


def get_handler(market_type):
    return REGISTRY.get(market_type)


def register(market_type, handler):
    REGISTRY.register(market_type, handler)
