# V0.3 数据库与 RAW 数据迁移方案（第四轮修订版）

> 基线：phase1 @ d39c7aa。  
> **本方案仅用于读取与分析，禁止在本轮执行任何数据库写入或迁移操作。**  
> 保存在 AndroidHarness 独立工作区 `v03_planning/`，**不修改 bb-node 仓库**。

---

## 1. 数据库分类与实际路径确认方法

### 1.1 三类数据库定义

| 类别 | 定义 | 示例路径（工作树中观测到） | 备注 |
|---|---|---|---|
| **生产数据库** | 核心采集服务正在使用的正式数据库 | `./data/bb.db`（按 database/db.py 配置为 `~/bb_node/data/bb.db`，实际路径需在阶段 0 确认） | **不得默认认定审计附件数据库为生产主数据库** |
| **审计附件数据库** | BB-D1 审计过程中保留的证据数据库 | `.harness/attachments/1101-100105-3eba6a0b-bb_audit_20261101_100026.db` | 33 MB，39 表（基于只读观测），包含历史数据；仅为证据数据库 |
| **测试数据库** | 测试用例使用的临时或固定数据库 | `./feature_test/data/bb.db`, `./audit/feature-bb-d1-v05-isolation-20261029/test_v05.db` 等 | 测试专用，不与生产数据混用 |

### 1.2 实际路径确认方法（只读，禁止写入）

阶段 0（经用户单独批准后）执行以下只读确认：

```bash
# 1. 读取 database/db.py 确认配置路径
cat database/db.py

# 2. 查找所有数据库文件（只读）
find . -maxdepth 6 \( -name "*.db" -o -name "*.sqlite" -o -name "*.sqlite3" -o -name "*.db3" \) 2>/dev/null

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
" <各数据库路径>
```

### 1.3 Schema 版本与实际结构确认

**重要说明**：`config/config.json` 中的 `schema_version: 11` **只能证明配置声明**，不能直接证明所有数据库实际 Schema 均为 11。

每类数据库（生产、审计附件、测试）必须分别检查真实表结构：

| 检查项 | 方法 | 目的 |
|---|---|---|
| 表清单 | `SELECT name FROM sqlite_master WHERE type='table' ORDER BY name` | 确认实际存在的表 |
| 列结构 | `PRAGMA table_info(<table>)` | 确认列名、类型、约束、默认值 |
| 索引 | `PRAGMA index_list(<table>)` 和 `PRAGMA index_info(<index>)` | 确认索引定义 |
| 外键 | `PRAGMA foreign_key_list(<table>)` | 确认外键关系 |
| WITHOUT ROWID | `SELECT sql FROM sqlite_master WHERE name='<table>'` | 确认是否为 WITHOUT ROWID 表 |
| 视图 | `SELECT name, sql FROM sqlite_master WHERE type='view'` | 确认视图定义 |
| 触发器 | `SELECT name, sql FROM sqlite_master WHERE type='trigger'` | 确认触发器定义 |

**不得**仅依据 config.json 中的 schema_version 声明推断任一数据库的实际 Schema。实际 Schema 以只读盘点结果为准，盘点前标记为**待确认**。

---

## 2. RAW 文件清单及实际存储路径确认方法

### 2.1 已知 RAW 目录（观测值，待阶段 0 确认）

| 路径 | 文件 | 备注 |
|---|---|---|
| `./data/raw/bb/` | `18dd2e22...json` (269 字节) | BB 源 RAW |
| `./data/raw/ladder/` | `4cb05f75...ladder`, `ec9b54fd...ladder` | 盘口 RAW |
| `./audit/bb-d1-ladder-adapter-20261029/data/raw/` | 未知 | BB-D1 盘口 RAW |
| `./audit/feature-bb-d1-v05-isolation-20261029/data/raw/` | 未知 | V05 隔离 RAW |

### 2.2 实际路径确认方法（只读）

```bash
find . -maxdepth 6 -type d \( -name "raw" -o -name "RAW" \) 2>/dev/null
find . -maxdepth 6 -type f \( -name "*.json" -o -name "*.ladder" -o -name "*.raw" -o -name "*.jsonl" -o -name "*.ndjson" \) 2>/dev/null | grep -v node_modules | grep -v .harness
```

---

## 3. Schema 版本权威来源（R3 明确）

### 3.1 唯一权威记录位置

**数据库 Schema 版本的唯一权威记录位于数据库本身**，具体为：

| 位置 | 说明 |
|---|---|
| **主数据库**：`PRAGMA user_version` 或专用元数据表 `schema_migrations(version, applied_at, description)` | 迁移执行成功后在同一事务中写入，作为数据库实际版本的单一真实来源 |
| **config.json** 中的 `schema_version` | **仅为配置声明**，表示代码期望的目标版本，**不能替代**数据库实际版本 |

**当前代码证据不足以确认项目已实现上述版本机制**。V0.3 阶段必须将其作为**待实现的设计要求**，不得声称已有机制。

### 3.2 迁移执行与版本记录的事务关系

迁移脚本执行必须满足：

1. **同一事务内**完成 DDL 变更与版本记录更新：
   ```sql
   BEGIN TRANSACTION;
   -- DDL 变更语句...
   INSERT INTO schema_migrations (version, applied_at, description) VALUES (?, datetime('now'), ?);
   -- 或 PRAGMA user_version = ?;
   COMMIT;
   ```
2. **失败自动回滚**：任一 DDL 失败，整个事务回滚，版本号不发生变更。
3. **幂等性**：迁移脚本开头检查当前版本，已应用则跳过。

### 3.3 迁移中断/失败时的实际版本识别

- **中断/失败时**：版本记录未更新，数据库仍处于迁移前版本。通过读取 `schema_migrations` 表最大版本或 `PRAGMA user_version` 即可识别实际版本。
- **部分表已变更但事务未提交**：SQLite 事务原子性保证不出现部分提交；重启后数据库自动回滚到迁移前状态。

### 3.4 版本记录的迁移前检查与迁移后验收用途

| 阶段 | 用途 |
|---|---|
| 迁移前检查 | 读取 `schema_migrations` 最大版本或 `user_version`，与迁移脚本目标版本对比，决定是否执行 |
| 迁移后验收 | 确认 `schema_migrations` 新增记录，版本号与目标一致；结构校验通过 |

---

## 4. 数据表依赖关系

```
collection_runs (批次)
    ├─► snapshots.collection_run_id
    │
matches ◄───────────────────┘
    │ source_match_id
    ▼
match_mappings ◄────────────┐
    │ canonical_match_id     │ market_id
    ▼                        ▼
market_mappings ◄───────────┘
    │ source_market_id
    ▼
unified_snapshots
    (events_v3, features_v2 等分析表，V0.3 不迁移)
```

**依赖顺序（迁移时必须遵守）：**
1. `matches` → `match_mappings`
2. `markets` → `market_mappings`
3. `match_mappings` + `market_mappings` → `unified_snapshots`
4. `collection_runs` → `snapshots`

---

## 5. 迁移顺序与脚本要求

| 步骤 | 操作 | 说明 |
|---|---|---|
| 1 | 只读盘点所有数据库与 RAW 文件 | 阶段 0（经用户单独批准后） |
| 2 | 只读盘点所有表结构与行数 | 建立基线，确认实际 Schema |
| 3 | 编写 001_initial.sql | 基于 phase1 schema_version 11 的**实际**表结构 |
| 4 | 编写 002_add_raw_ledger.sql | 添加 raw_records / raw_observations / unmapped_records |
| 5 | 编写 003_add_mapping_indexes.sql | 添加缺失索引，确保唯一键兼容 |
| 6 | 在数据库副本上执行迁移 | **禁止在生产 DB 直接执行** |
| 7 | 数量、结构、数据核验 | 见 §7, §8 |
| 8 | 生产迁移必须单独获得用户批准后执行 | 阶段 4 |
| 9 | 迁移失败时回滚 | 见 V03_ROLLBACK_PLAN.md |

### 5.1 迁移脚本结构检测与兼容性要求

对已有 RAW ledger 的数据库（如 phase1 已有 `raw_records`、`raw_observations`、`unmapped_records` 表），迁移脚本**必须具备结构检测和兼容性判断**，不能只依赖 `CREATE TABLE IF NOT EXISTS` 就认定迁移安全。

迁移脚本必须：
1. **检测表是否存在**：`SELECT name FROM sqlite_master WHERE type='table' AND name=?`
2. **检测表结构是否与目标一致**：对比 `PRAGMA table_info` 结果（列名、类型、NOT NULL、默认值、主键）
3. **检测索引是否与目标一致**：对比 `PRAGMA index_list` 和 `PRAGMA index_info`
4. **对不一致情况给出明确处理策略**：跳过（已兼容）、ALTER TABLE（可安全变更）、或中止并报告（需人工介入）
5. **记录检测结果**：每个迁移步骤输出检测日志，便于审计

`CREATE TABLE IF NOT EXISTS` 仅作为幂等性辅助，**不是**结构兼容性的充分证明。

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

**风险点**：`save_mapping()` 的 ON CONFLICT DO UPDATE 会无条件覆盖 canonical_match_id，可能将已有 CID 更新为 NULL。V0.3 必须修复为：仅在新 CID 不为 NULL 时才更新，或保留旧值（B5）。

---

## 7. 数据量校验

迁移前后必须对每张表进行以下校验：

| 校验项 | 方法 | 通过标准 |
|---|---|---|
| 行数一致 | `SELECT COUNT(*)` 迁移前 vs 迁移后 | 完全相等 |
| 结构一致 | `PRAGMA table_info()` 对比 | 列名、类型、约束完全相等 |
| 索引一致 | `PRAGMA index_list()` 对比 | 索引名称、列、唯一性完全相等 |
| 外键一致 | `PRAGMA foreign_key_list()` 对比 | 外键关系完全相等 |
| 数据核验 | 见 §8 规范化数据核验方案 | 按表类型执行对应核验 |
| 样本抽查 | 随机 100 行逐字段对比 | 字段值完全相等 |

---

## 8. 数据核验方案（设计要求，待实现）

### 8.1 数据库文件 SHA256 的用途限制

**数据库文件 SHA256 只用于备份文件完整性验证，不作为迁移前后数据库相同的判断标准。**

迁移可能改变数据库文件的内部布局（页大小、WAL 状态、索引重建、free page 等），因此 `.db` 文件本身的 SHA256 在迁移前后**不应要求相同**，也**不得**用作迁移成功的判定依据。

### 8.2 RAW 文件 SHA256

RAW 文件在迁移中不应被修改，RAW 文件的 SHA256 迁移前后应保持一致：

```bash
sha256sum ./data/raw/bb/*.json ./data/raw/ladder/*.ladder > raw_before.sha256
# 迁移后
sha256sum ./data/raw/bb/*.json ./data/raw/ladder/*.ladder > raw_after.sha256
diff raw_before.sha256 raw_after.sha256
```

### 8.3 表级规范化数据核验（设计要求）

**未变更表**使用规范化数据核验，**变更表**使用明确的数据映射核验。

以下为规范化数据核验的设计要求，**尚未实现可执行代码**，不得声称已实现：

#### 8.3.1 稳定排序要求

**不得在未定义稳定排序方式时直接使用 `ORDER BY rowid`。**

- **有稳定主键的普通表**：按主键列排序（`ORDER BY <pk_columns>`）
- **有稳定唯一键的表**：按唯一键列排序
- **WITHOUT ROWID 表**：按表定义的 PRIMARY KEY 排序
- **无稳定主键且无稳定唯一键的表**：必须先定义稳定排序列组合（如所有列的确定性排序），并在迁移脚本中明确记录；若无法定义稳定排序，标记为**待实现**，不得使用不确定排序

#### 8.3.2 各类型对象的哈希处理

| 对象类型 | 处理方式 | 状态 |
|---|---|---|
| 普通表（有稳定主键） | 按主键排序抽取所有行，规范化序列化后计算 SHA256 | 设计要求，待实现 |
| WITHOUT ROWID 表 | 按 PRIMARY KEY 排序抽取所有行，规范化序列化后计算 SHA256 | 设计要求，待实现 |
| BLOB 列 | BLOB 内容转为十六进制字符串（如 `hex()`）后参与序列化 | 设计要求，待实现 |
| NULL 值 | 使用显式 NULL 标记（如 JSON `null`），不得与空字符串混淆 | 设计要求，待实现 |
| 视图 | 无数据，仅校验 `CREATE VIEW` 语句文本的一致性 | 设计要求，待实现 |
| 无稳定主键的表 | 必须先定义稳定排序方式，否则标记为待实现 | 设计要求，待实现 |
| 变更表 | 不做全表哈希对比，使用明确的数据映射核验（逐字段映射规则 + 样本/全量对比） | 设计要求，待实现 |

#### 8.3.3 变更表的数据映射核验

对结构或数据发生变更的表，必须：
1. 在迁移脚本中明确记录每个字段的映射关系（源字段 → 目标字段、转换规则）
2. 逐行核验映射正确性（或对大表进行分批抽样核验，抽样策略需明确）
3. 记录核验结果，不得以“迁移脚本执行成功”替代数据核验

---

## 9. SQLite WAL 一致性备份方式

SQLite 在 WAL 模式下，数据可能分布在主数据库文件和 WAL 文件中。备份时必须确保一致性：

**允许的备份方式（二选一，必须明确选择）**：

| 方式 | 说明 | 前提条件 |
|---|---|---|
| **SQLite online backup API**（推荐） | 使用 `sqlite3.Connection.backup()` 或等价 API | 数据库可正常打开 |
| **明确停写 + WAL 检查点** | 停止所有写入进程，执行 `PRAGMA wal_checkpoint(TRUNCATE)`，确认返回成功后复制 .db/.wal/.shm 文件 | 必须确保无写入进程，检查点必须成功 |

**禁止的方式**：
- 直接复制未检查点的 WAL 模式数据库文件（.db + .wal + .shm）而不执行检查点或 online backup
- 在有活跃写入进程时执行文件复制

**备份验证**：
- 备份文件可正常打开（`sqlite3 <backup> "PRAGMA integrity_check;"`）
- 备份文件的表清单和行数与源一致（在停写状态下）

---

## 10. 迁移失败回滚方案

### 10.1 预防措施

1. **全量备份**：迁移前备份所有 `.db` 文件、RAW 目录、配置文件（使用 WAL 一致性备份方式）
2. **副本测试**：先在数据库副本上执行迁移脚本，验证无误
3. **事务封装**：每个迁移脚本在单个事务中执行，失败自动回滚
4. **版本标记**：迁移完成后写入 `schema_migrations` 或 `user_version`，下次迁移前检查当前版本
5. **生产迁移必须单独获得用户批准**

### 10.2 回滚步骤（不得默认 rm -rf，不得直接覆盖原始数据库）

```
1. 停止所有采集与写入程序
2. 将迁移后的数据库文件重命名为失败副本（不删除）
   mv <db_path> <db_path>.migration_failed_<timestamp>
3. 从备份恢复数据库文件到新路径（不直接覆盖原文件）
   使用 SQLite online backup API 或经停写+检查点的备份文件
   恢复到 <db_path>.restored_<timestamp>
4. 验证恢复完整性
   - 备份文件完整性 SHA256 与备份时记录一致（仅验证备份未损坏）
   - 所有表行数与备份前一致
   - 表结构与备份前一致
   - RAW 文件 SHA256 与备份前一致
5. 如验证通过，将恢复文件替换为生产路径（经用户确认后）
   mv <db_path>.restored_<timestamp> <db_path>
6. 从备份恢复 RAW 目录到新路径（不删除原目录）
   cp -r ./backup/<timestamp>/data/raw/ ./data/raw.restored_<timestamp>
7. 验证 RAW 文件 SHA256 与备份前一致
8. 重新启动采集程序，确认可正常读写
```

详见 V03_ROLLBACK_PLAN.md。

---

## 11. 原始数据备份和恢复方案

### 11.1 备份范围

| 类别 | 路径 | 备份方式 | 频率 |
|---|---|---|---|
| 生产数据库 | 生产 `.db` 文件 | SQLite online backup API 或停写+检查点后复制 | 迁移前、每日定期 |
| 审计附件数据库 | `.harness/attachments/` 下 `.db` | 文件复制或 backup API | 迁移前 |
| 测试数据库 | 测试 `.db` 文件 | 文件复制 | 按需 |
| RAW 文件 | `./data/raw/` | 目录复制 | 迁移前、每日定期 |
| 配置 | `config/config.json`, `config/node.json` | 文件复制 | 变更时 |

### 11.2 备份存储

- 备份目录：`./backup/<timestamp>/`（新目录，不覆盖现有备份）
- 保留策略：保留最近 5 个版本，旧版本由用户决定是否删除
- 备份完整性：每次备份后生成 SHA256 清单（用于验证备份文件未损坏），恢复时校验

### 11.3 RAW 原始数据与推断、标准化数据分层保存

| 层 | 存储位置 | 说明 | V0.3 是否保留 |
|---|---|---|---|
| RAW 原始层 | `data/raw/bb/<sha256>.json` | 原始 API 响应，不修改、不覆盖 | 是 |
| 标准化层 | database (snapshots, unified_snapshots) | 标准化后的记录 | 是 |
| 推断层 | match_mappings.canonical_match_id 等 | 由匹配算法推断，可重新计算 | 是（RAW 不依赖推断） |

**原则**：RAW 原始数据永远不因标准化或推断失败而丢弃。异常 RAW 数据完整保存，状态标记为 `unmatched` 或 `pending_review`，等待业务确认。

---

## 12. 禁止事项（本轮）

- 禁止运行任何可能写入数据库的程序
- 禁止执行数据库迁移脚本
- 禁止修改、删除或覆盖任何 `.db` 文件
- 禁止修改、删除或覆盖任何 RAW 文件
- 禁止在 `data/` 目录下创建新文件
- 禁止默认认定审计附件数据库为生产主数据库
- 禁止要求原始数据库文件哈希与迁移后文件哈希相同
- 禁止在未定义稳定排序方式时直接使用 `ORDER BY rowid`
- 禁止在有活跃写入进程时进行文件级数据库复制
- 禁止声称未实现的哈希方案已经实现
- 禁止声称 Schema 版本机制已实现（当前为待实现设计要求）
