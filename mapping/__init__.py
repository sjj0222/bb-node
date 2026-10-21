# P3-19/P3-17: import 期不再建表——此前 init_mapping()/init_market_mapping()/
# init_unified() 在 import 时抢先建出老结构残表(CREATE TABLE IF NOT EXISTS
# 让 db.init() 的权威建表变 no-op, 只能靠迁移补列)。建表统一由
# database.db.init() 负责(权威 DDL + 幂等迁移 + 列断言)。
from .db import init_mapping
from .market_db import init_market_mapping
from .unified_db import init_unified
