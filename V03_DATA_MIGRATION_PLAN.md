# V0.3 数据库与 RAW 数据迁移方案

> 基线：phase1 (`d39c7aa`)。  
> **本方案仅用于读取与分析，禁止在本轮执行任何数据库写入或迁移操作。**

---

## 1. 当前数据库清单及实际路径确认方法

### 1.1 已知数据库文件

| 路径 | 大小 | 表数量 | 备注 |
|---|---|---|---|
| `./data/bb.db` | 未知（需确认） | 未知 | 主数据库（按 database/db.py 配置 `~/bb_node/data/bb.db`，实际工作树中为 `./data/bb.db`） |
| `.harness/attachments/1101-100105-3eba6a0b-bb_audit_20261101_100026.db` | 33,038,336 字节 | 39 表 | 审计附件数据库，包含完整历史数据 |
| `./feature_test/data/bb.db` | 未知 | 未知 | 测试数据库 |
| `./audit/bb_d1/data/` 下数据库 | 未知 | 未知 | BB-D1 审计数据 |
| `./audit/bb-d1-ladder-adapter-20261029/data/` | 未知 | 未知 | BB-D1 盘口适配器数据 |
| `./audit/feature-bb-d1-v05-isolation-20261029/data/` | 未知 | 未知 | V05 隔离测试数据 |
| `./d1_iso_tmp/feature_test/data/bb.db` | 未知 | 未知 | 隔离测试临时数据 |

### 1.2 实际路径确认方法（只读，禁止写入）

```bash
# 1. 读取 database/db.py 确认配置路径
cat database/db.py

# 2. 查找所有数据库文件（只读）
find . -maxdepth 5 \( -name "*.db" -o -name "*.sqlite" -o -name "*.sqlite3" -o -name "*.db3" \) 2>/dev/null

# 3. 对每个数据库只读查看表结构与行数（禁止写入）
python3 -c "
import sqlite3, sys
for path in sys.argv[1:]:
    c = sqlite3.connect(f'file:{path}?mode=ro', uri=True)
    print(f'=== {path} ===')
    for (t,) in c.execute(\"SELECT name FROM sqlite_master WHERE type='table' ORDER BY name\"):
        n = c.execute(f'SELECT COUNT(*) FROM [{t}]').fetchone()[0]
        print(f'  {t}: {n} rows')
    c.close()
" .harness/attachments/1101-100105-3eba6a0b-bb_audit_20261101_100026.db ./data/bb.db
```

### 1.3 当前主数据库 Schema 版本

从 `config/config.json`（phase1）：`schema_version: 11`。  
从 `database/db.py`（当前工作树）：无显式版本字段，通过 `CREATE TABLE IF NOT EXISTS` 隐式管理。

审计附件数据库（39 表）包含完整历史：
- `matches` (215 行), `markets` (3023 行), `snapshots` (40542 行), `unified_snapshots` (37699 行)
- `collection_runs` (99 行), `match_mappings` (628 行), `market_mappings` (6253 行)
- `events_v3` (2699 行), `event_groups_v3` (10 行), `features_v2` (6 行)
- `replay_events_v2` (1154 行), `replay_runs_v2` (1 行), `signals_v1` (4 行)
- `decisions_v1` (2 行), `strategies_v1` (2 行), `source_health` (1 行), `pipeline_runs` (102 行)

---

## 2. RAW 文件清单及实际存储路径确认方法

### 2.1 已知 RAW 目录

| 路径 | 文件 | 备注 |
|---|---|---|
| `./data/raw/bb/` | `18dd2e22...json` (269 字节) | BB 源 RAW |
| `./data/raw/ladder/` | `4cb05f75...ladder` (61 字节), `ec9b54fd...ladder` (76 字节) | 盘口 RAW |
| `./audit/bb-d1-ladder-adapter-20261029/data/raw/` | 未知 | BB-D1 盘口 RAW |
| `./audit/feature-bb-d1-v05-isolation-20261029/data/raw/` | 未知 | V05 隔离 RAW |
| `./audit/feature-bb-d1-v05-isolation-20261029/raw/` | 未知 | V05 隔离 RAW 根 |

### 2.2 实际路径确认方法（只读）

```bash
# 1. 查找所有 RAW 目录与文件
find . -maxdepth 6 -type d \( -name "raw" -o -name "RAW" \) 2>/dev/null
find . -maxdepth 6 -type f \( -name "*.json" -o -name "*.ladder" -o -name "*.raw" -o -name "*.jsonl" -o -name "*.ndjson" \) 2>/dev/null | grep -v node_modules | grep -v .harness

# 2. 计算文件 SHA256（只读）
sha256sum ./data/raw/bb/*.json ./data/raw/ladder/*.ladder
```

---

## 3. Schema 版本盘点

| 数据库 | Schema 版本 | 版本管理方式 | 表列表（核心） |
|---|---|---|---|
| `./data/bb.db` | 未显式标记 | CREATE TABLE IF NOT EXISTS | matches, markets, snapshots, collection_runs, match_mappings, unified_snapshots |
| 审计附件 DB | schema_version 11（config 推断） | config.json + 创建脚本 | 39 表（含完整分析表） |
| 测试 DB | 未知 | 未知 | 未知 |

**问题**：当前工作树的 `database/db.py` 没有 schema 版本字段，无法自动判断数据库是否需要迁移。V0.3 必须在 `database/migrations/` 中建立显式版本管理。

---

## 4. 数据表依赖关系

```
collection_runs (批次)
    │
    ├─► snapshots.collection_run_id ────┐
    │                                   │
matches ◄───────────────────────────────┤
    │                                   │
    │ source_match_id                   │ match_id
    ▼                                   ▼
match_mappings ◄──────────────────────────────┐
    │                                         │
    │ canonical_match_id                      │ market_id
    ▼                                         ▼
market_mappings ◄─────────────────────────────┘
    │
    │ source_market_id
    ▼
unified_snapshots ◄──────────────────────────┐
    │                                        │
    │ canonical_match_id                     │ collection_run_id
    ▼                                        ▼
(events_v3, features_v2 等分析表，V0.3 不迁移)
```

**依赖顺序（迁移时必须遵守）：**
1. `matches` → `match_mappings`（source_match_id 关联）
2. `markets` → `market_mappings`（market_id 关联）
3. `match_mappings` + `market_mappings` → `unified_snapshots`（canonical_match_id + source_market_id 关联）
4. `collection_runs` → `snapshots`（collection_run_id 外键）

---

## 5. 迁移顺序

| 步骤 | 操作 | 说明 |
|---|---|---|
| 1 | 备份所有数据库与 RAW 文件 | 阶段 0 完成 |
| 2 | 只读盘点所有表结构与行数 | 建立基线 |
| 3 | 建立 `database/migrations/`，编写 001_initial.sql | 基于 phase1 schema_version 11 |
| 4 | 编写 002_add_raw_ledger.sql | 添加 raw_records / raw_observations / unmapped_records（如 phase1） |
| 5 | 编写 003_add_mapping_indexes.sql | 添加缺失索引，确保唯一键兼容 |
| 6 | 在测试环境（副本 DB）执行迁移 | 禁止在生产 DB 直接执行 |
| 7 | 数量、结构、SHA256 校验 | 对比迁移前后 |
| 8 | 如校验通过，备份生产 DB 后执行迁移 | 阶段 4 |
| 9 | 迁移失败时回滚 | 见 §9 |

---

## 6. 唯一键和索引兼容性

| 表 | 现有唯一键/索引 | V0.3 目标 | 兼容性说明 |
|---|---|---|---|
| `match_mappings` | UNIQUE(source, source_match_id) | 保留 | 兼容 |
| `market_mappings` | UNIQUE(source, source_match_id, source_market_id, option) | 保留 | 兼容 |
| `unified_snapshots` | UNIQUE(source, source_match_id, source_market_id, option, received_at) | 保留 | 兼容 |
| `snapshots` | UNIQUE(node_id, match_id, market_id, option_index, collected_at, data_hash) | 保留 | 兼容 |
| `matches` | PRIMARY KEY(match_id) | 保留 | 兼容 |
| `markets` | PRIMARY KEY(market_id) | 保留 | 兼容 |
| `collection_runs` | PRIMARY KEY(id) AUTOINCREMENT | 保留 | 兼容 |

**风险点**：`save_mapping()` 的 ON CONFLICT DO UPDATE 会无条件覆盖 canonical_match_id，可能将已有 CID 更新为 NULL。V0.3 必须修复为：仅在新 CID 不为 NULL 时才更新，或保留旧值。

---

## 7. 数据量校验

迁移前后必须对每张表进行以下校验：

| 校验项 | 方法 | 通过标准 |
|---|---|---|
| 行数一致 | `SELECT COUNT(*)` 迁移前 vs 迁移后 | 完全相等 |
| 结构一致 | `PRAGMA table_info()` 对比 | 列名、类型、约束完全相等 |
| 索引一致 | `PRAGMA index_list()` 对比 | 索引名称、列、唯一性完全相等 |
| 外键一致 | `PRAGMA foreign_key_list()` 对比 | 外键关系完全相等 |
| 数据哈希 | 对每张表全量数据计算 SHA256 | 迁移前后哈希值一致 |
| 样本抽查 | 随机 100 行逐字段对比 | 字段值完全相等 |

---

## 8. SHA256 校验

### 8.1 数据库文件 SHA256

```bash
sha256sum ./data/bb.db > db_before.sha256
# 迁移后
sha256sum ./data/bb.db > db_after.sha256
diff db_before.sha256 db_after.sha256
```

### 8.2 RAW 文件 SHA256

```bash
sha256sum ./data/raw/bb/*.json ./data/raw/ladder/*.ladder > raw_before.sha256
# 迁移后
sha256sum ./data/raw/bb/*.json ./data/raw/ladder/*.ladder > raw_after.sha256
diff raw_before.sha256 raw_after.sha256
```

### 8.3 表级数据 SHA256

```python
import sqlite3, hashlib, json
c = sqlite3.connect('file:./data/bb.db?mode=ro', uri=True)
for (t,) in c.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"):
    rows = c.execute(f"SELECT * FROM [{t}] ORDER BY rowid").fetchall()
    h = hashlib.sha256(json.dumps(rows, ensure_ascii=False, sort_keys=True).encode()).hexdigest()
    print(f"{t}: {h} ({len(rows)} rows)")
c.close()
```

---

## 9. 迁移失败回滚方案

### 9.1 预防措施

1. **全量备份**：迁移前备份所有 `.db` 文件、RAW 目录、配置文件。
2. **只读测试**：先在数据库副本上执行迁移脚本，验证无误后再执行生产库。
3. **事务封装**：每个迁移脚本在单个事务中执行，失败自动回滚。
4. **版本标记**：迁移完成后写入 `schema_version`，下次迁移前检查当前版本。

### 9.2 回滚步骤

```
1. 停止所有采集与写入程序
2. 删除/重命名迁移后的数据库文件
3. 从备份恢复数据库文件（cp backup/bb.db data/bb.db）
4. 从备份恢复 RAW 目录（cp -r backup/raw/ data/raw/）
5. 验证恢复后的行数与 SHA256 与迁移前一致
6. 重新启动采集程序，确认可正常读写
```

### 9.3 回滚验证标准

- 数据库文件 SHA256 与备份前一致
- 所有表行数与备份前一致
- 采集程序可正常启动并读取数据
- 无数据丢失或损坏

---

## 10. 原始数据备份和恢复方案

### 10.1 备份范围

| 类别 | 路径 | 备份方式 | 频率 |
|---|---|---|---|
| 数据库 | `./data/bb.db` + WAL/SHM | 文件复制 | 迁移前、每日定期 |
| RAW 文件 | `./data/raw/` | 目录复制 | 迁移前、每日定期 |
| 配置 | `config/config.json`, `config/node.json` | 文件复制 | 变更时 |
| 审计证据 | `.harness/attachments/` 下数据库 | 文件复制 | 迁移前 |

### 10.2 备份存储

- 备份目录：`./backup/<timestamp>/`
- 保留策略：保留最近 5 个版本，旧版本由用户决定是否删除。
- 备份完整性：每次备份后生成 SHA256 清单，恢复时校验。

### 10.3 恢复流程

```bash
# 1. 确认备份完整性
sha256sum -c backup/<timestamp>/backup.sha256

# 2. 停止程序
# 3. 恢复数据库
cp backup/<timestamp>/data/bb.db ./data/bb.db
# 4. 恢复 RAW
cp -r backup/<timestamp>/data/raw/ ./data/raw/
# 5. 验证
python3 verify_restore.py  # 行数 + SHA256 校验
# 6. 重启程序
```

### 10.4 RAW 原始数据与推断、标准化数据分层保存

| 层 | 存储位置 | 说明 | V0.3 是否保留 |
|---|---|---|---|
| RAW 原始层 | `data/raw/bb/<sha256>.json` | 原始 API 响应，不修改、不覆盖 | 是 |
| 标准化层 | `database/db.py` (snapshots, unified_snapshots) | 标准化后的记录 | 是 |
| 推断层 | `match_mappings.canonical_match_id` 等 | 由匹配算法推断，可重新计算 | 是（但RAW不依赖推断） |

**原则**：RAW 原始数据永远不因标准化或推断失败而丢弃。即使 `event_time=None` 或 CID 生成失败，RAW 文件仍完整保存，状态标记为 `unmatched` 或 `pending_review`，等待业务确认。

---

## 11. 禁止事项（本轮）

- 禁止运行任何可能写入数据库的程序。
- 禁止执行数据库迁移脚本。
- 禁止修改、删除或覆盖任何 `.db` 文件。
- 禁止修改、删除或覆盖任何 RAW 文件。
- 禁止在 `data/` 目录下创建新文件。
