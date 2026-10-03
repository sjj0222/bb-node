from .bb import BBAdapter
from .sx import SXBetAdapter
from core import env

ADAPTERS = {
    "bb": BBAdapter,
    "sx": SXBetAdapter,
}


def get_adapter(source):
    cls = ADAPTERS.get(source)
    if not cls:
        raise ValueError("unknown source: " + source)
    return cls()


def enabled_sources():
    """按 config sources.<name>.enabled 返回启用的 source 名列表。"""
    cfg = env.get("sources") or {}
    out = []
    for name in ADAPTERS:
        sc = cfg.get(name) or {}
        if sc.get("enabled", True):
            out.append(name)
    return out
