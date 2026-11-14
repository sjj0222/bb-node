# V0.3 目标架构报告（第四轮修订版）

> 基线：phase1 @ d39c7aa。  
> 本文件仅用于读取与分析，保存在 AndroidHarness 独立工作区 `v03_planning/`，**不修改 bb-node 仓库**。

---

## 1. 设计原则

1. **采集层与数据存储层分离**：采集逻辑不直接操作 SQL，通过 Repository/DAO 接口写入。
2. **RAW 与标准化数据分离**：RAW 原始文件与数据库表物理分离，RAW 文件不被标准化过程修改。
3. **比赛映射与盘口映射分离**：match_mappings 与 market_mappings 独立表、独立索引、独立生命周期。
4. **数据库迁移脚本独立管理**：schema 版本与迁移脚本置于 `database/migrations/`，不与运行代码混杂。
5. **导出功能独立**：export 模块不依赖采集链路，仅读取数据库与 RAW 文件。
6. **客户端与核心业务逻辑解耦**：客户端仅通过 API 调用核心服务，不嵌入采集逻辑。
7. **P2P 和高级分析模块可后续接入**：预留接口，不影响基础采集。
8. **V0.3 不要求交付可安装 APK/EXE**：V0.3 只完成客户端架构规划、接口定义和必要目录预留。创建客户端目录不等于 APK/EXE 可交付，实际构建、签名、打包属于后续独立工作。

---

## 2. 目标目录结构（V0.3）

```
bb-node/
├── config/
│   ├── config.json              # 运行配置（阶段版本、数据库路径、RAW 目录、源列表）
│   └── node.json                # 节点标识（运行时生成，不提交）
├── core/
│   ├── __init__.py
│   ├── collector.py             # 采集编排（V0.3 必须）
│   ├── log.py                   # 采集日志
│   ├── status.py                # 状态查询
│   └── repository.py            # 数据访问抽象层
├── database/
│   ├── __init__.py
│   ├── db.py                    # SQLite 连接、PRAGMA、初始化
│   ├── schema.sql               # 基础 Schema DDL
│   └── migrations/              # 迁移脚本独立管理
│       ├── 001_initial.sql
│       ├── 002_add_raw_ledger.sql
│       └── 003_add_mapping_indexes.sql
├── data/                        # 运行时数据目录（不提交，.gitignore）
│   ├── bb.db                    # 正式数据库（核心服务唯一写入）
│   └── raw/
│       ├── bb/
│       └── ladder/
├── mapping/
│   ├── __init__.py
│   ├── match.py
│   ├── market.py
│   ├── db.py
│   ├── market_db.py
│   ├── unified_db.py
│   ├── unified_service.py
│   └── service.py
├── sources/
│   ├── __init__.py
│   ├── base.py
│   ├── bb.py
│   └── registry.py
├── export/
│   ├── __init__.py
│   ├── json_export.py
│   └── csv_export.py
├── pipeline/
│   ├── __init__.py
│   └── orchestrator.py          # 简化版采集管道（COLLECT → NORMALIZE → MAPPING → UNIFIED）
├── client/
│   ├── android/                 # Android 客户端架构目录（仅预留，非可交付 APK）
│   │   ├── app/
│   │   ├── build.gradle
│   │   └── AndroidManifest.xml
│   └── windows/                 # Windows 客户端架构目录（仅预留，非可交付 EXE）
│       ├── main.py / .cs
│       └── *.spec / *.csproj
├── scripts/
│   ├── backup.py
│   └── restore.py
├── tests/
│   ├── test_mapping_match.py
│   ├── test_mapping_market.py
│   ├── test_line.py
│   ├── test_export.py
│   └── conftest.py
├── main.py
├── VERSION
├── .gitignore
└── README.md
```

---

## 3. 各目录用途、依赖与是否进入 V0.3

| 目录 | 用途 | 依赖 | 进入 V0.3 | 备注 |
|---|---|---|---|---|
| `config/` | 运行配置，阶段版本 | 无 | 是 | config.json 从 phase1 填充，node.json 运行时生成 |
| `core/` | 采集编排、日志、状态、存储抽象 | database, sources, mapping | 是 | |
| `database/` | SQLite 连接、Schema、迁移脚本 | 无 | 是 | migrations/ 独立管理版本 |
| `data/` | 运行时数据库与 RAW 文件 | 无 | 是 | 仅运行时，不提交代码 |
| `mapping/` | 比赛映射、盘口映射、统一写入 | database, sources | 是 | match/market 分离 |
| `sources/` | 源适配器、RAW 保存、标准化 | core.base | 是 | |
| `export/` | JSON/CSV 导出 | database, data/raw | 是 | |
| `pipeline/` | 简化版采集管道 | core, sources, mapping, export | 是 | |
| `client/android/` | Android 客户端架构目录 | 核心服务 API | 是（架构仅） | **仅预留目录，不等于 APK 可交付** |
| `client/windows/` | Windows 客户端架构目录 | 核心服务 API | 是（架构仅） | **仅预留目录，不等于 EXE 可交付** |
| `scripts/` | 备份与恢复 | database, data | 是 | 方案与规范（V0.3 不要求工具可执行，见 §8） |
| `tests/` | 单元测试与集成测试 | 所有核心模块 | 是 | |
| `events/` ~ `p2p/` | 分析/同步模块 | — | 否 | 后续阶段（V0.4+），仅预留接口 |

---

## 4. 客户端访问架构

### 4.1 核心采集服务运行位置

核心采集服务（`core/collector.py`、`pipeline/orchestrator.py`、`mapping/`、`sources/`、`database/`）运行于**独立后台进程或服务器**，不运行在 Android 或 Windows 客户端内。客户端不承担采集职责，仅负责数据展示与配置。

**架构决策项（待最终确定）**：核心服务的具体部署位置（同设备本地服务、局域网服务器、或远程服务器）尚未最终确定。在最终确定前，不得自行假设部署位置；同设备部署和跨设备部署的差异（网络、认证、延迟）必须在后续决策中明确。

### 4.2 SQLite 主数据库唯一写入责任方

**核心服务进程是 SQLite 主数据库的唯一写入责任方**。所有对主数据库（`data/bb.db` 及其 WAL/SHM）的写操作必须由核心服务进程发起并完成。

### 4.3 客户端访问方式

- **Android 和 Windows 客户端通过 API 访问核心服务**，不得直接读写核心服务 SQLite 文件。
- **同设备部署也必须通过本地 API 或明确的进程间接口**（如 HTTP localhost、Unix domain socket、命名管道等），**不得以共享 SQLite 文件作为默认方案**。
- 跨设备部署通过远程 API（HTTPS/HTTP）访问。
- 客户端仅通过 API 读取数据、提交配置请求，不持有数据库写锁。

### 4.4 SQLite 文件读写责任划分

| 角色 | 读写权限 | 说明 |
|---|---|---|
| 核心服务进程 | 读写 | 唯一写入责任方，负责采集、映射、统一、导出数据源 |
| Android 客户端 | 无直接访问 | 仅通过 API 读取，不直接读写核心服务 SQLite 文件 |
| Windows 客户端 | 无直接访问 | 仅通过 API 读取，不直接读写核心服务 SQLite 文件 |

### 4.5 客户端数据目录

| 平台 | 数据目录 | 用途 |
|---|---|---|
| Android | 应用私有目录（如 `/data/data/<package>/files/` 或 `getExternalFilesDir()`） | 客户端缓存、配置、导出文件副本；**不存储核心服务主数据库** |
| Windows | `%APPDATA%\BB-Node\` 或用户文档目录 | 客户端配置、缓存、导出文件副本；**不存储核心服务主数据库** |

### 4.6 客户端升级与用户数据

- 客户端安装包升级时，仅替换程序文件（APK/EXE 及相关资源），不触碰用户数据目录。
- 用户配置、缓存、导出文件存储在与程序文件分离的数据目录中，升级保留。
- 客户端不负责核心服务数据库的升级，数据库迁移由核心服务独立管理。

### 4.7 版本与 API 兼容策略（架构决策项）

| 项目 | 状态 | 说明 |
|---|---|---|
| 核心服务 API 版本策略 | 待明确 | API 需包含版本标识（如 `/api/v1/`），版本升级策略待定义 |
| 客户端与核心服务兼容矩阵 | 待明确 | 客户端最低/最高兼容的核心服务 API 版本需明确 |
| 不兼容时的降级/提示策略 | 待明确 | 客户端检测到 API 不兼容时的行为（提示升级、只读降级等）待定义 |
| 配置与数据格式版本 | 待明确 | 客户端配置格式、导出数据格式的版本兼容策略待定义 |

**以上项目为架构决策项，在最终确定前不得自行假设。**

---

## 5. 数据流向（V0.3）——含 Unified 准入闸门

```
BB Adapter API
      │
      ▼
核心采集服务（独立后台进程/服务器，唯一写入方）
  sources/bb.BBAdapter.save_raw() ─────────► data/raw/bb/<sha256>.json  (RAW 原始，不覆盖)
  sources/bb.BBAdapter.normalize() ───────► NormalizedRecord (标准化记录)
      │
      ▼
  core/collector.collect() ───────────────► database/db: collection_runs (批次记录)
      │
      ├─► mapping/db.save_mapping() ───► match_mappings (比赛映射)
      ├─► mapping/market_db.save() ───► market_mappings (盘口映射)
      │        │
      │        ▼
      │  ┌─────────────────────────────────────┐
      │  │  身份与盘口语义准入检查               │
      │  │  - B1: event_time 确认               │
      │  │  - B2: source_market_id 语义确认      │
      │  │  - B3: CID 字段完整/碰撞风险          │
      │  │  - B4: Unified NULL CID 策略          │
      │  │  - B5/B6: 写入链路安全修复验收         │
      │  └─────────────────────────────────────┘
      │        │
      ▼        ▼
  mapping/unified_db.save_unified() ──► unified_snapshots (统一快照)
      │
      ▼
  export/json_export.py / csv_export.py ──► 导出文件 (JSON/CSV)
      │
      ▼
核心服务 API (本地 API / IPC / 远程 API)
      │
      ▼
Android 客户端 / Windows 客户端 ────► 通过 API 读取数据，展示与配置
```

**准入规则（必须在代码与架构中体现）：**

- **B1-B4 未确认的数据不得被当作已确认数据写入 Unified**。
- **未确认的数据进入 "pending_review" 或相应隔离状态**。
- **只有满足准入条件的数据才允许进入 Unified**。
- **B5/B6 未修复并完成验收前，相关 Unified 写入链路不得启用**。

---

## 6. 接口预留（后续阶段接入点）

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

## 7. 过度拆分避免说明

- 未单独建立 `models/`、`services/`、`adapters/` 目录，现有模块职责已足够清晰。
- `client/android` 与 `client/windows` 仅为 V0.3 目录框架（架构预留），具体实现由客户端团队按需填充，核心库不依赖客户端。
- V0.3 不交付可安装的 APK 或 EXE，客户端实际构建属于后续独立工作。

---

## 8. 备份与恢复交付范围（R4 统一）

| 项目 | V0.3 交付定义 |
|---|---|
| **备份与恢复方案** | ✅ 必须交付：完整的操作规范、流程文档、备份目录结构、校验清单、回滚步骤、WAL 一致性备份方式 |
| **备份恢复工具（scripts/backup.py, scripts/restore.py）** | ❌ **不要求实际可执行工具**，仅交付接口定义、参数规范、调用契约与方案文档 |
| **验收标准** | 方案文档完整、流程清晰、可由人工执行并验证；不要求自动化脚本通过验收 |

> **统一说明**：V03_SCOPE.md、V03_TARGET_ARCHITECTURE.md、V03_ACCEPTANCE.md 均采用上述定义。范围要求方案与规范，架构定义接口契约，验收条件为方案文档完整性与可人工执行性，不要求工具代码已实现并通过测试。
