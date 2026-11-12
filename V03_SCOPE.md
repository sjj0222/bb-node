# V0.3 范围定义报告（第三轮修订版）

> 基线：phase1 @ d39c7aa。  
> 本文件仅用于读取与分析，保存在 AndroidHarness 独立工作区 `v03_planning/`，**不修改 bb-node 仓库**。

---

## 1. V0.3 基础交付产品目标

| 序号 | 功能 | 说明 | 依赖模块 | 进入 V0.3 |
|---|---|---|---|---|
| 1 | 自动采集 | 定时/手动从 BB Adapter 采集比赛与盘口数据 | core/collector, sources/bb, mapping/, database/ | 是 |
| 2 | RAW 原始数据完整保存 | 原始响应按内容哈希命名，分层保存，不覆盖，异常 RAW 不静默丢弃 | sources/bb.save_raw, data/raw/, database/raw_records | 是 |
| 3 | 正式数据库落库 | SQLite，匹配/盘口/快照/统一/映射/批次表 | database/db.py, mapping/db.py, mapping/market_db.py, mapping/unified_db.py | 是 |
| 4 | 采集批次与历史追溯 | collection_runs 记录每次采集，支持按批次查询历史 | database/db.py collection_runs | 是 |
| 5 | JSON/CSV 导出 | 导出比赛、盘口、快照、映射数据 | pipeline / export 模块（需从 phase1/v0.2 提取） | 是 |
| 6 | Android 客户端架构规划 | 客户端架构规划、接口定义、必要目录预留 | 新增 | 是（仅架构规划） |
| 7 | Windows 客户端架构规划 | 客户端架构规划、接口定义、必要目录预留 | 新增 | 是（仅架构规划） |

**重要说明**：
- V0.3 **只完成**客户端架构规划、接口定义和必要目录预留。V0.3 **不要求交付**可安装的 APK 或 EXE。
- 创建 `client/android/`、`client/windows/` 目录**不等于** APK/EXE 已经可交付。客户端构建、签名、打包属于后续独立工作。

---

## 2. 后续阶段功能（明确延期，不进入 V0.3）

| 序号 | 功能 | 延期理由 | 预计阶段 |
|---|---|---|---|
| 8 | Android APK 可安装交付 | V0.3 仅完成架构规划，构建/签名/打包属后续独立工作 | V0.4+ |
| 9 | Windows EXE 可安装交付 | 同上 | V0.4+ |
| 10 | P2P 多节点同步 | 需网络协议、节点发现、冲突解决，属高级架构 | V0.4+ |
| 11 | Event / Feature / Signal | 属分析模块，V0.3 仅需采集与落库，下游分析可后续接入 | V0.4+ |
| 12 | Strategy / Decision | 依赖 Signal，属业务决策层 | V0.5+ |
| 13 | Replay / Backtest | 依赖 Event/Feature，属历史回溯分析 | V0.4+ |
| 14 | 高级盘口分析 | 依赖完整事件与特征链路 | V0.5+ |

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
| `core/collector.py` | 采集编排，调用适配器与映射 | database, sources, mapping | 是 | 需修复：区分 CONFLICT（业务状态）与 IntegrityError（数据库约束） |
| `sources/bb.py` | BB Adapter，RAW 保存与标准化 | core.base.NormalizedRecord | 是 | 需保留 save_raw 扩展（经审计后合并） |
| `sources/base.py` | NormalizedRecord 定义 | 无 | 是 | 纯数据类，无风险 |
| `sources/registry.py` | 源注册表 | 无 | 是 | 轻量 |
| `database/db.py` | SQLite 连接、Schema 初始化、核心表 | 无 | 是 | 需确认 DB 路径统一，添加 schema 版本字段 |
| `mapping/db.py` | 比赛映射表 match_mappings | database.db | 是 | save_mapping 需修复 NULL CID 覆盖（B5） |
| `mapping/match.py` | canonical_match_id 生成与匹配评分 | 无 | 是 | CID 字段需扩展（B3，待业务确认后） |
| `mapping/market.py` | 盘口归一化 | 无 | 是 | 与比赛映射分离 |
| `mapping/market_db.py` | 盘口映射表 market_mappings | database.db | 是 | 与比赛映射分离 |
| `mapping/unified_db.py` | 统一快照表 unified_snapshots | database.db | 是 | 允许 NULL CID 需业务确认（B4） |
| `mapping/unified_service.py` | 统一写入服务 | mapping.db, mapping.unified_db | 是 | |
| `mapping/service.py` | 自动映射编排 | mapping.db, mapping.match | 是 | |
| `core/log.py` | 采集日志（start/finish/error） | 无 | 是 | 轻量 |
| `core/status.py` | 状态查询 | database.db | 是 | 轻量 |
| `config/config.json` | 配置（phase1 已填充） | 无 | 是 | 作为 V0.3 配置基点 |

**可延期的模块（V0.3 不进入，后续接入）：**

| 模块 | 理由 | 预计阶段 |
|---|---|---|
| `events/engine_v3.py` | Event 引擎，属分析层 | V0.4+ |
| `features/engine_v2.py` | Feature 引擎 | V0.4+ |
| `signals/engine_v1.py` | 依赖 Feature | V0.5+ |
| `strategies/engine_v1.py` | 依赖 Signal | V0.5+ |
| `decisions/engine_v1.py` | 依赖 Strategy | V0.5+ |
| `replay/` | 重放引擎 | V0.4+ |
| `backtest/` | 回测引擎 | V0.4+ |
| `monitor/monitor.py` | 监控 | V0.4+ |
| `p2p/node.py` | P2P 节点 | V0.4+ |
| `client/android/` | 客户端目录（架构规划，非可交付 APK） | V0.3 架构，APK 后续交付 |
| `client/windows/` | 客户端目录（架构规划，非可交付 EXE） | V0.3 架构，EXE 后续交付 |

---

## 4. B1-B6 业务定义待确认事项与统一阻塞规则

### 4.1 统一阻塞规则（R1-R6）

| 规则 | 说明 |
|---|---|
| R1 | 原始采集和 RAW 保存可以继续。 |
| R2 | 未确认身份的数据不得被当作已确认比赛写入 Unified。 |
| R3 | 未确认盘口语义的数据不得被错误合并。 |
| R4 | Unified 写入必须具有明确的允许条件、隔离条件和状态记录。 |
| R5 | 异常记录不得被静默丢弃。 |
| R6 | B1-B6 必须在 V0.3 验收前明确标记为待业务确认或已修复，不得擅自决定业务定义。 |

### 4.2 B1-B6 分类与准入条件

**分类原则**：
- **B1-B4**：待业务定义事项，不等于基础采集和 RAW 保存必须停止；但未确认身份/盘口语义的数据不得被当作已确认数据写入 Unified。
- **B5、B6**：已发现的代码安全问题，**必须在启用相关写入链路前修复并验收**。

**各链路准入条件**：

| 链路 | 准入条件 | B1-B6 影响 |
|---|---|---|
| 基础采集 | RAW 可正常获取并保存 | R1：B1-B4 不阻塞采集；采集过程中的数据库写入必须满足 B5/B6 修复后的安全条件 |
| RAW 保存 | 原始响应按内容哈希命名，不覆盖 | R1, R5：B1-B4 不阻塞 RAW 保存，异常 RAW 完整保留并标记状态 |
| 映射（match/market mapping） | 映射逻辑可执行，但未确认身份的记录必须标记状态 | B1-B3 不阻塞映射执行，但映射结果中未确认记录不得视为已确认；B5 影响映射写入安全 |
| Unified 写入 | 必须满足 R2、R3、R4：身份已确认、盘口语义已确认或已隔离、有明确允许条件和状态记录 | B1-B4 未确认时，相关数据**不得**进入 Unified（作为已确认数据）；B5/B6 必须修复后才允许相关写入链路启用 |

### 4.3 B1-B6 具体事项

| 序号 | 事项 | 类型 | 现状 | 阻塞规则 | V0.3 处理方式 | 对各链路的影响 |
|---|---|---|---|---|---|---|
| B1 | `event_time=None` 的业务处理 | 待业务定义 | 未最终确定 | R1, R2, R5, R6 | 标记为待业务确认，RAW 完整保存，不静默丢弃；未确认身份的数据不得写入 Unified | 不阻塞采集和 RAW 保存；阻塞该记录作为已确认比赛写入 Unified |
| B2 | `source_market_id` 合并或隔离语义 | 待业务定义 | 未确认 | R1, R3, R5, R6 | 标记为待业务确认，不合并也不隔离，保留原始数据；未确认盘口语义不得错误合并 | 不阻塞采集和 RAW 保存；阻塞盘口语义未确认数据的错误合并写入 |
| B3 | CID 生成字段不完整，同名球队同一分钟时间桶碰撞风险 | 待业务定义 | 未确认 | R1, R2, R5, R6 | 标记为待业务确认，RAW 完整保存；Unified 写入前需人工或规则确认身份 | 不阻塞采集和 RAW 保存；阻塞未确认身份数据写入 Unified |
| B4 | Unified 允许 NULL CID | 待业务定义 | 未确认 | R2, R4, R6 | 标记为待业务确认；NULL CID 记录不得视为已确认比赛写入 Unified，需明确隔离条件和状态记录 | 不阻塞采集和 RAW 保存；阻塞 NULL CID 记录作为已确认比赛进入 Unified |
| B5 | `save_mapping()` 可能将已有 CID 更新为 NULL | 代码安全问题 | 已发现 | R4, R6 | **必须在启用映射写入链路前修复并验收**：仅在新 CID 不为 NULL 时更新，或保留旧值 | 阻塞未修复的映射写入链路启用 |
| B6 | Collector 漏拦截 CONFLICT / 未区分 IntegrityError | 代码安全问题 | 已发现 | R1, R4, R5, R6 | **必须在启用相关写入链路前修复并验收**：区分 CONFLICT（业务状态）与 IntegrityError（数据库约束），分别处理，不得用 IntegrityError 捕获代替业务状态判断 | 阻塞未修复的采集写入链路启用 |

**明确说明**：B1-B4 未解决不等于基础采集和 RAW 保存必须停止，但**绝不允许**未确认身份或未确认盘口语义的数据被当作已确认数据写入 Unified。B5、B6 作为代码安全问题，必须在启用相关写入链路前修复并通过验收，不得将其描述为“完全不阻塞”。

---

## 5. 当前工作区未提交内容处理原则

以下文件**不得**覆盖、删除或擅自纳入提交，必须在阶段 0（经用户单独批准后）只读盘点时单独记录：

- `sources/bb.py` 的用户修改（save_raw raw_content 扩展、normalize 增强）
- `core/collector.py.bak`、`events/engine_v3.py.bak`、`export_today.py` 及其备份
- `sources/ladder.py`、`fix_engine_v2.py`、`history_query.py`、`pipeline_runner.py`、`test_write.txt`
- `tests/test_pipeline_runner.py`、`tests/test_replay_pairing.py`
- 其他异常命名的未跟踪文件

处理方式：在阶段 0（经用户单独批准后）只读盘点并记录，阶段 7 验收后由用户决定是否合并、归档或删除。**未得到用户单独批准前，不得执行冻结、备份或任何修改。**

---

## 6. 范围变更控制

- V0.3 范围一旦确定，任何新增功能均需通过变更请求，不得悄悄纳入。
- 后续阶段功能（APK/EXE 实际交付、P2P、Event/Feature/Signal、Strategy/Decision、Replay/Backtest、高级盘口分析）原则上不进入 V0.3，除非用户明确批准并调整验收标准。
- 业务定义待确认事项（B1-B6）不得以“丢弃异常 RAW 数据”的方式解决，必须保留原始数据并标记状态。
- B1-B4 的业务定义未确认时，不得擅自决定；B5、B6 必须修复后才能启用相关写入链路。
