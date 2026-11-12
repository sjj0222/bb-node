# V0.3 范围定义报告（修订版）

> 基线：phase1 @ d39c7aa。  
> 本文件仅用于读取与分析，保存在 AndroidHarness 独立工作区 `v03_planning/`，**不修改 bb-node 仓库**。

---

## 1. V0.3 基础交付产品目标（必须全部交付）

| 序号 | 功能 | 说明 | 依赖模块 | 进入 V0.3 |
|---|---|---|---|---|
| 1 | 自动采集 | 定时/手动从 BB Adapter 采集比赛与盘口数据 | core/collector, sources/bb, mapping/, database/ | 是 |
| 2 | RAW 原始数据完整保存 | 原始响应按内容哈希命名，分层保存，不覆盖，异常 RAW 不静默丢弃 | sources/bb.save_raw, data/raw/, database/raw_records | 是 |
| 3 | 正式数据库落库 | SQLite，匹配/盘口/快照/统一/映射/批次表 | database/db.py, mapping/db.py, mapping/market_db.py, mapping/unified_db.py | 是 |
| 4 | 采集批次与历史追溯 | collection_runs 记录每次采集，支持按批次查询历史 | database/db.py collection_runs | 是 |
| 5 | JSON/CSV 导出 | 导出比赛、盘口、快照、映射数据 | pipeline / export 模块（需从 phase1/v0.2 提取） | 是 |
| 6 | Android APK | 核心业务逻辑与客户端解耦，可安装运行 | 新增（不在任何候选分支中） | 是 |
| 7 | Windows EXE | 同上 | 新增（不在任何候选分支中） | 是 |

**重要说明**：创建客户端目录（`client/android/`、`client/windows/`）**不等于** APK/EXE 已经可交付。客户端构建、签名、打包属于后续独立工作，V0.3 阶段仅负责架构规划与接口预留。

---

## 2. 后续阶段功能（明确延期，不进入 V0.3）

| 序号 | 功能 | 延期理由 | 预计阶段 |
|---|---|---|---|
| 8 | P2P 多节点同步 | 需网络协议、节点发现、冲突解决，属高级架构 | V0.4+ |
| 9 | Event / Feature / Signal | 属分析模块，V0.3 仅需采集与落库，下游分析可后续接入 | V0.4+ |
| 10 | Strategy / Decision | 依赖 Signal，属业务决策层 | V0.5+ |
| 11 | Replay / Backtest | 依赖 Event/Feature，属历史回溯分析 | V0.4+ |
| 12 | 高级盘口分析 | 依赖完整事件与特征链路 | V0.5+ |

---

## 3. 基础交付的必要依赖模块（按真实调用关系）

从 phase1 及当前工作树梳理，V0.3 基础采集链路的实际调用关系如下：

```
main.py / pipeline.orchestrator
  └── core/collector.collect()
        ├── sources/bb.BBAdapter (save_raw / normalize)
        │     └── mapping/match.make_canonical_id
        ├── mapping/service.auto_map
        │     └── mapping/db.save_mapping
        ├── mapping/unified_service.unify
        │     └── mapping/unified_db.save_unified
        ├── database/db.init / connect
        └── core/log (start / finish / error)
```

**必须保留的模块（V0.3 必选）：**

| 模块 | 用途 | 依赖 | 进入 V0.3 | 备注 |
|---|---|---|---|---|
| `core/collector.py` | 采集编排，调用适配器与映射 | database, sources, mapping | 是 | 需修复 CONFLICT 处理，不得用 IntegrityError 代替业务状态判断 |
| `sources/bb.py` | BB Adapter，RAW 保存与标准化 | core.base.NormalizedRecord | 是 | 需保留 save_raw 扩展（经审计后合并） |
| `sources/base.py` | NormalizedRecord 定义 | 无 | 是 | 纯数据类，无风险 |
| `sources/registry.py` | 源注册表 | 无 | 是 | 轻量 |
| `database/db.py` | SQLite 连接、Schema 初始化、核心表 | 无 | 是 | 需确认 DB 路径统一，添加 schema 版本字段 |
| `mapping/db.py` | 比赛映射表 match_mappings | database.db | 是 | save_mapping 需修复 NULL CID 覆盖 |
| `mapping/match.py` | canonical_match_id 生成与匹配评分 | 无 | 是 | CID 字段需扩展（业务确认后） |
| `mapping/market.py` | 盘口归一化 | 无 | 是 | 与比赛映射分离 |
| `mapping/market_db.py` | 盘口映射表 market_mappings | database.db | 是 | 与比赛映射分离 |
| `mapping/unified_db.py` | 统一快照表 unified_snapshots | database.db | 是 | 允许 NULL CID 需业务确认 |
| `mapping/unified_service.py` | 统一写入服务 | mapping.db, mapping.unified_db | 是 | |
| `mapping/service.py` | 自动映射编排 | mapping.db, mapping.match | 是 | |
| `core/log.py` | 采集日志（start/finish/error） | 无 | 是 | 轻量 |
| `core/status.py` | 状态查询 | database.db | 是 | 轻量 |
| `config/config.json` | 配置（phase1 已填充） | 无 | 是 | 作为 V0.3 配置基点 |

**可延期的模块（V0.3 不进入，后续接入）：**

| 模块 | 理由 | 预计阶段 |
|---|---|---|
| `events/engine_v3.py` | Event 引擎，属分析层 | V0.4+ |
| `features/engine_v2.py` | Feature 引擎，存在全表 DELETE 与 cutoff 不一致缺陷 | V0.4+ |
| `signals/engine_v1.py` | 依赖 Feature | V0.5+ |
| `strategies/engine_v1.py` | 依赖 Signal | V0.5+ |
| `decisions/engine_v1.py` | 依赖 Strategy | V0.5+ |
| `replay/event_v1.py` / `event_v2.py` | 重放引擎 | V0.4+ |
| `backtest/engine_v1.py` / `v2.py` | 回测引擎 | V0.4+ |
| `monitor/monitor.py` | 监控（当前 0 字节） | V0.4+ |
| `p2p/node.py` | P2P 节点（当前 0 字节） | V0.4+ |
| `pipeline/orchestrator.py` | 虽在 phase1 中，但 V0.3 可简化为核心采集链路 | V0.3 简化版 |
| `client/android/` | Android 客户端目录（架构规划，非可交付 APK） | V0.3 架构，APK 后续交付 |
| `client/windows/` | Windows 客户端目录（架构规划，非可交付 EXE） | V0.3 架构，EXE 后续交付 |

---

## 4. B1-B6 业务定义待确认事项与统一阻塞规则

### 4.1 统一阻塞规则（适用于所有 B1-B6）

| 规则 | 说明 |
|---|---|
| R1 | 原始采集和 RAW 保存可以继续，不因业务未确认而停止采集或删除 RAW 数据。 |
| R2 | 未确认身份的数据不得被当作已确认比赛写入 Unified。 |
| R3 | 未确认盘口语义的数据不得被错误合并，不同 source_market_id 的盘口实例不得自动合并或隔离，保留原始数据。 |
| R4 | Unified 写入必须有明确的允许条件、隔离条件和状态记录，不允许未经确认的数据进入 Unified。 |
| R5 | 异常记录不得被静默丢弃，必须有状态标记（如 pending_review / unmatched）。 |
| R6 | 业务定义事项（B1-B6）必须在 V0.3 验收前明确标记状态，不得自行决策。 |

### 4.2 B1-B6 具体事项

| 序号 | 事项 | 现状 | 阻塞规则 | V0.3 处理方式 | 是否阻塞 V0.3 |
|---|---|---|---|---|---|
| B1 | `event_time=None` 的业务处理 | 所有候选均未最终确定 | R1, R2, R5 | 标记为待业务确认，RAW 数据完整保存，不静默丢弃，Unified 写入前需确认 | 是（映射层） |
| B2 | `source_market_id` 来自 BB Adapter `mk.id`，一个市场组可存在多个盘口实例 | Market Selector 不区分 source_market_id | R1, R3, R5 | 标记为待业务确认，不合并也不隔离，保留原始数据 | 是（映射层） |
| B3 | CID 生成字段不完整，同名球队同一分钟时间桶碰撞风险 | make_canonical_id 仅 home\|away\|event_time//60000 | R1, R2, R5 | 标记为待业务确认，RAW 数据完整保存，Unified 写入前需人工或规则确认 | 是（映射层） |
| B4 | Unified 允许 NULL CID | unified_snapshots.canonical_match_id 允许 NULL | R2, R4 | 业务确认后决定是否加 NOT NULL 约束 | 是（数据库） |
| B5 | `save_mapping()` 可能将已有 CID 更新为 NULL | ON CONFLICT DO UPDATE 无条件覆盖 | R4 | 修复为仅在新 CID 不为 NULL 时更新，或保留旧值 | 是（数据库写入安全） |
| B6 | Collector 漏拦截 CONFLICT | 采集写入无唯一约束保护 | R1, R4 | 在收集写入层区分 CONFLICT（业务状态）与 IntegrityError（数据库约束），分别处理 | 是（采集链路） |

---

## 5. 当前工作区未提交内容处理原则（V0.3 范围内）

以下文件**不得**覆盖、删除或擅自纳入提交，必须在阶段 0 冻结后单独盘点：

- `sources/bb.py` 的用户修改（save_raw raw_content 扩展、normalize 增强）
- `core/collector.py.bak`
- `events/engine_v3.py.bak`
- `export_today.py` 及其备份
- `sources/ladder.py`
- `fix_engine_v2.py`
- `history_query.py`
- `pipeline_runner.py`
- `test_write.txt`
- `tests/test_pipeline_runner.py`
- `tests/test_replay_pairing.py`
- 其他异常命名的未跟踪文件

处理方式：在阶段 0 将上述文件拷贝至只读备份目录，阶段 7 验收后由用户决定是否合并、归档或删除。**不得在阶段 0 之前擅自冻结工作区或执行备份。**

---

## 6. 范围变更控制

- V0.3 范围一旦确定，任何新增功能均需通过变更请求，不得悄悄纳入。
- 后续阶段功能（P2P、Event、Feature、Signal、Strategy、Decision、Replay、Backtest、高级盘口分析）原则上不进入 V0.3，除非用户明确批准并调整验收标准。
- 业务定义待确认事项（B1-B6）不得以“丢弃异常 RAW 数据”的方式解决，必须保留原始数据并标记状态。
