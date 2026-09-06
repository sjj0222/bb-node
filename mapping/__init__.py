from .db import init_mapping
from .market_db import init_market_mapping
from .unified_db import init_unified

init_mapping()
init_market_mapping()
init_unified()
