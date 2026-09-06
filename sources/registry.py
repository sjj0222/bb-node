from .bb import BBAdapter

ADAPTERS = {
    "bb": BBAdapter,
}

def get_adapter(source):
    cls = ADAPTERS.get(source)
    if not cls:
        raise ValueError("unknown source: " + source)
    return cls()
