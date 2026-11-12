# V0.3 目标架构报告

> 基线：phase1 (`d39c7aa`)。  
> 仅用于读取与分析，未执行任何写入。

---

## 1. 设计原则

1. **采集层与数据存储层分离**：采集逻辑不直接操作 SQL，通过 Repository/DAO 接口写入。
2. **RAW 与标准化数据分离**：RAW 原始文件与数据库表物理分离，RAW 文件不被标准化过程修改。
3. **比赛映射与盘口映射分离**：match_mappings 与 market_mappings 独立表、独立索引、独立生命周期。
4. **数据库迁移脚本独立管理**：schema 版本与迁移脚本置于 `database/migrations/`，不与运行代码混杂。
5. **导出功能独立**：export 模块不依赖采集链路，仅读取数据库与 RAW 文件。
6. **Android、Windows 客户端与核心业务逻辑解耦**：客户端仅调用核心库的 REST/本地 API，不嵌入采集逻辑。
7. **P2P 和高级分析模块可后续接入**：预留接口，不影响基础采集。

---

## 2. 目标目录结构（V0.3）

```
bb-node/
├── config/
│   ├── config.json              # 运行配置（阶段版本、数据库路径、RAW 目录、源列表）
│   └── node.json                # 节点标识（运行时生成，不提交）
├── core/
│   ├── __init__.py
│   ├── collector.py             # 采集编排（V0.3 必须，从 phase1 精简）
│   ├── log.py                   # 采集日志（start/finish/error）
│   ├── status.py                # 状态查询
│   └── repository.py            # 数据访问抽象层（采集层与存储层分离的桥梁）
├── database/
│   ├── __init__.py
│   ├── db.py                    # SQLite 连接、PRAGMA、初始化
│   ├── schema.sql               # 基础 Schema DDL（版本 1）
│   └── migrations/              # 迁移脚本独立管理
│       ├── 001_initial.sql
│       ├── 002_add_raw_ledger.sql
│       └── 003_add_mapping_indexes.sql
├── data/                        # 运行时数据目录（不提交，.gitignore）
│   ├── bb.db                    # 正式数据库
│   └── raw/
│       ├── bb/                  # BB 源 RAW 原始文件（内容哈希命名）
│       └── ladder/              # 盘口 RAW 原始文件
├── mapping/
│   ├── __init__.py
│   ├── match.py                 # canonical_match_id 生成与比赛匹配（V0.3 必须）
│   ├── market.py                # 盘口归一化（与比赛映射分离）
│   ├── db.py                    # match_mappings 表操作（V0.3 必须，修复 save_mapping）
│   ├── market_db.py             # market_mappings 表操作（V0.3 必须）
│   ├── unified_db.py            # unified_snapshots 表操作（V0.3 必须）
│   ├── unified_service.py       # 统一写入服务（V0.3 必须）
│   └── service.py               # 自动映射编排（V0.3 必须）
├── sources/
│   ├── __init__.py
│   ├── base.py                  # NormalizedRecord 定义
│   ├── bb.py                    # BB Adapter：RAW 保存 + 标准化（V0.3 必须，保留未提交扩展经审计后合并）
│   └── registry.py              # 源注册表
├── export/
│   ├── __init__.py
│   ├── json_export.py           # JSON 导出（V0.3 必须）
│   └── csv_export.py            # CSV 导出（V0.3 必须）
├── pipeline/
│   ├── __init__.py
│   └── orchestrator.py          # 简化版采集管道（COLLECT → NORMALIZE → MAPPING → UNIFIED）
├── client/
│   ├── android/                 # Android 源码（新增，与核心解耦）
│   │   ├── app/
│   │   ├── build.gradle
│   │   └── AndroidManifest.xml
│   └── windows/                 # Windows 源码（新增，与核心解耦）
│       ├── main.py / .cs
│       └── *.spec / *.csproj
├── scripts/
│   ├── backup.py                # 数据库与 RAW 备份（V0.3 必须）
│   └── restore.py               # 数据库与 RAW 恢复（V0.3 必须）
├── tests/
│   ├── test_mapping_match.py    # 纯函数单元测试
│   ├── test_mapping_market.py
│   ├── test_line.py             # 采集解析测试
│   ├── test_export.py           # 导出测试
│   └── conftest.py
├── main.py                      # V0.3 入口：python -m pipeline.orchestrator
├── VERSION                      # 0.3.0
├── .gitignore
└── README.md
```

---

## 3. 各目录用途、依赖与是否进入 V0.3

| 目录 | 用途 | 依赖 | 进入 V0.3 | 备注 |
|---|---|---|---|---|
| `config/` | 运行配置，阶段版本 | 无 | 是 | config.json 从 phase1 填充，node.json 运行时生成 |
| `core/` | 采集编排、日志、状态、存储抽象 | database, sources, mapping | 是 | repository.py 新增，实现采集/存储分离 |
| `database/` | SQLite 连接、Schema、迁移脚本 | 无 | 是 | migrations/ 新增，独立管理版本 |
| `data/` | 运行时数据库与 RAW 文件 | 无 | 是 | 仅运行时，不提交代码 |
| `mapping/` | 比赛映射、盘口映射、统一写入 | database, sources | 是 | match/market 分离，save_mapping 修复 |
| `sources/` | 源适配器、RAW 保存、标准化 | core.base | 是 | bb.py 需保留 save_raw 扩展（经审计后合并） |
| `export/` | JSON/CSV 导出 | database, data/raw | 是 | 新增模块，从 phase1/v0.2 提取导出逻辑 |
| `pipeline/` | 简化版采集管道 | core, sources, mapping, export | 是 | 从 phase1 pipeline.orchestrator 精简，去除 Event/Feature/Strategy 等下游阶段 |
| `client/android/` | Android APK 源码 | 核心库（通过本地 API 调用） | 是 | 新增，与核心解耦，V0.3 仅需安装运行 |
| `client/windows/` | Windows EXE 源码 | 核心库（通过本地 API 调用） | 是 | 新增，与核心解耦，V0.3 仅需安装运行 |
| `scripts/` | 备份与恢复 | database, data | 是 | 新增，V0.3 必须具备备份恢复能力 |
| `tests/` | 单元测试与集成测试 | 所有核心模块 | 是 | 从 phase1 提取纯函数测试，新增导出测试 |
| `events/` | 事件引擎 | mapping, database | 否 | 后续阶段（V0.4+），预留接口 |
| `features/` | 特征引擎 | events | 否 | 后续阶段（V0.4+），预留接口 |
| `signals/` | 信号引擎 | features | 否 | 后续阶段（V0.5+） |
| `strategies/` | 策略引擎 | signals | 否 | 后续阶段（V0.5+） |
| `decisions/` | 决策引擎 | strategies | 否 | 后续阶段（V0.5+） |
| `replay/` | 重放引擎 | events, features | 否 | 后续阶段（V0.4+） |
| `backtest/` | 回测引擎 | replay | 否 | 后续阶段（V0.4+） |
| `monitor/` | 监控 | database | 否 | 后续阶段（V0.4+） |
| `p2p/` | P2P 节点 | 网络层 | 否 | 后续阶段（V0.4+） |

---

## 4. 数据流向（V0.3）

```
BB Adapter API
      │
      ▼
sources/bb.BBAdapter.save_raw() ─────────► data/raw/bb/<sha256>.json  (RAW 原始，不覆盖)
      │
      ▼
sources/bb.BBAdapter.normalize() ───────► NormalizedRecord (标准化记录)
      │
      ▼
core/collector.collect() ───────────────► database/db: collection_runs (批次记录)
      │
      ├─► mapping/db.save_mapping() ───► match_mappings (比赛映射)
      ├─► mapping/market_db.save() ───► market_mappings (盘口映射)
      ├─► mapping/unified_db.save_unified() ──► unified_snapshots (统一快照)
      └─► database/db: snapshots (采集快照)
      │
      ▼
export/json_export.py / csv_export.py ──► 导出文件 (JSON/CSV)
      │
      ▼
client/android / client/windows ──► 读取导出文件或直接查询数据库
```

---

## 5. 接口预留（后续阶段接入点）

| 预留点 | 位置 | 用途 | V0.3 是否实现 |
|---|---|---|---|
| Event 总线 | `events/engine.py` | 事件发布/订阅 | 否（仅预留目录） |
| 特征计算 | `features/engine.py` | 从统一快照计算特征 | 否 |
| 信号生成 | `signals/engine.py` | 从特征生成交易信号 | 否 |
| 策略引擎 | `strategies/engine.py` | 从信号生成策略 | 否 |
| 决策执行 | `decisions/engine.py` | 从策略生成决策 | 否 |
| 重放接口 | `replay/engine.py` | 历史数据回放 | 否 |
| P2P 同步 | `p2p/node.py` | 多节点数据同步 | 否 |

---

## 6. 客户端解耦方案

- **核心库**：以 Python 库形式提供，所有业务逻辑位于 `core/`, `mapping/`, `sources/`, `database/`, `export/`。
- **Android 客户端**：通过本地 SQLite 数据库文件或导出的 JSON/CSV 读取数据，不嵌入 Python 采集逻辑。UI 层独立，仅负责展示与配置。
- **Windows 客户端**：同上，通过读取共享数据目录 (`~/bb_node/data/` 或配置指定路径) 获取数据。
- **数据路径**：客户端与核心库共享同一数据目录，路径由 `config/config.json` 统一配置，升级时不覆盖用户数据。

---

## 7. 过度拆分避免说明

- 未单独建立 `models/` 目录：NormalizedRecord 等轻量数据类已在 `sources/base.py` 定义，无需额外拆分。
- 未单独建立 `services/` 目录：mapping/service.py 已承担编排职责，无需再拆。
- 未单独建立 `adapters/` 目录：sources/ 下已按源分目录，当前仅 BB 源，无需额外抽象层。
- `client/android` 与 `client/windows` 仅在 V0.3 新增目录框架，具体实现由客户端团队按需填充，核心库不依赖客户端。
