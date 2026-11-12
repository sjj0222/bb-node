# V0.3 候选基线比较报告（修订版）

> 基线：phase1 @ d39c7aa（推荐），v0.2 @ 35ea228（参考）。  
> 本文件仅用于读取与分析，保存在 AndroidHarness 独立工作区 `v03_planning/`，**不修改 bb-node 仓库**。

---

## 1. 候选基线一览表

| 候选 | 提交哈希 | 角色 | 相对 main 的提交数 | 文件数 | 测试文件 | 导出功能 | 批次追溯 | Schema/Migration | 平台客户端 | 配置 |
|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| **phase1** | `d39c7aa` | 推荐基线 | +20 | 128 | 31 | 是 | 是（pipeline_runs/trace_id） | 是（schema_version 11） | 无 | 已填充（0.3.0-rc1） |
| **v0.2** | `35ea228` | 参考基线 | +5 | 94 | 16 | 是 | 是（collection_runs） | 是（schema_version 11） | 无 | 已填充 |
| **main** | `74cff43` | 修补来源 | 0 | 49 | 0 | 否 | 最小（2 表） | 是（基础表） | 无 | 空（0 B） |
| **delivery/bb-d1-p0-2-p0-3-20261029** | `d7637e4` | 修补来源 | +6 | 56 | 3 | 否 | 最小 | 是 | 无 | 空 |
| **audit/bb-d1-canonical-match-id-hardening-20261029** | `f46251b` | 修补来源 | +12 | 64 | 4 | 否 | 最小 | 是 | 无 | 空 |
| **impl/bb-node-tdd-20261026（当前工作树）** | `b1581d7` | 修补来源 | +7 | 57 | 1 | 否 | 最小 | 是 | 无 | 空 |

*注：file/test 数为远程分支树内的文件计数，working tree 另有未跟踪与未提交修改。*

---

## 2. 共同祖先与提交历史

所有候选分支的 merge-base 与 `main` 均为 `74cff43` 本身，即：**main 是所有其他候选的直接祖先，所有候选均为 main 的线性后代，不存在分支分叉与合并冲突问题。**

各分支提交主题（摘要）：

- **phase1 (d39c7aa)**: +20 条，主题包括 Phase 1-13 完整功能（packaging、docs、release candidate、稳定性阈值、事件/特征/信号/策略/决策/重放/回测/监控/P2P 等）以及审计修复 P0-P3。版本号 `0.3.0-rc1`。
- **v0.2 (35ea228)**: +5 条，主题包括 V0.1 双源 E2E、V0.2 接受报告、P2P RAW 同步语义、Monitor 异常保护等。带有 `ACCEPTANCE_V0.2.md`。
- **impl-tdd (b1581d7)**: +7 条，主题包括负零解析、BB-D1 N08-N18 审计笔记等。当前工作树在此基础上还有未提交修改。
- **delivery/bb-d1-p0-2-p0-3 (d7637e4)**: +6 条，主题为 BB-D1 P0.2/P0.3 修复，包括源 market_id 保护、canonical_match_id 恢复、唯一约束测试等。
- **audit/bb-d1-canonical-match-id-hardening (f46251b)**: +12 条，主题为 BB-D1 P0.3.2 唯一约束测试修复、canonical_match_id 恢复等，包含大量测试文件。
- **main (74cff43)**: 基础设施 commit，15 条提交，最新为 `feat: add pipeline stale health checks`。

---

## 3. 功能维度详细对比

### 3.1 自动采集能力

| 候选 | 采集层 | 源适配器 | 采集入口 | 失败处理 | 批次记录 |
|---|---|---|---|---|---|
| phase1 | core/collector.py + core/checks/core/health | sources/bb.py, sources/sx.py | pipeline.orchestrator run_pipeline() | 分阶段 try/except，trace_id 链路追踪 | collection_runs + pipeline_runs + trace_id |
| v0.2 | core/collector.py | sources/bb.py, sources/sx.py | pipeline.orchestrator (COLLECT stage) | try/except 分阶段记录，有 collection_runs | collection_runs + pipeline_runs |
| main | core/collector.py | sources/bb.py | main.py → collect() | 基础 try/except，失败写入 collection_runs | collection_runs 仅 |
| delivery | 同 main | sources/bb.py | main.py → collect() | 同上 | collection_runs 仅 |
| audit-hardening | 同 main | sources/bb.py | main.py → collect() | 同上 | collection_runs 仅 |
| impl-tdd | 同 main | sources/bb.py（未提交修改） | main.py → collect() | 同上 | collection_runs 仅 |

### 3.2 RAW 原始数据保存能力

| 候选 | RAW 目录 | RAW 内容哈希 | 幂等写入 | RAW 账本表 | 说明 |
|---|---|---|---|---|---|
| phase1 | env.raw_dir(source) | SHA256 文件名 | 是（ON CONFLICT source,content_hash） | raw_records / raw_observations / unmapped_records | 最完整的 RAW 分层账本 |
| v0.2 | data/raw/bb | SHA256 文件名 | 是 | raw_records / raw_observations | 次之 |
| main | data/raw/bb | SHA256 文件名 | 是（文件级不覆盖） | 无账本表，仅文件 | 基础 RAW 文件保存 |
| delivery | 同上 | 同上 | 是 | 无账本表 | 同上 |
| audit-hardening | 同上 | 同上 | 是 | 无账本表 | 同上 |
| impl-tdd | 同上 | 同上 | 是 | 无账本表 | 同上（working tree 中 sources/bb.py 有未提交的 save_raw 扩展） |

### 3.3 数据库结构

| 候选 | 核心表 | 映射表 | 统一表 | 分析表 | 客户端/同步表 |
|---|---|---|---|---|---|
| phase1 | matches, markets, collection_runs, snapshots + stability_runs, dq_runs, backtest_runs_v1/v2, replay_runs_v1/v2 | match_mappings, market_mappings | unified_snapshots | events_v3, event_groups_v3, features_v2, replay_events_v2, decisions_v1, strategies_v1 | nodes, source_health, pipeline_runs, watchlist, alerts |
| v0.2 | 同 phase1 精简版 | match_mappings, market_mappings | unified_snapshots | 同 phase1 精简版 | 同 phase1 |
| main | matches, markets, collection_runs, snapshots | match_mappings | unified_snapshots | 无 | nodes |
| delivery | 同 main | match_mappings | unified_snapshots | 无 | nodes |
| audit-hardening | 同 main | match_mappings（唯一约束测试） | unified_snapshots | 无 | nodes |
| impl-tdd | 同 main | match_mappings | unified_snapshots | 无 | nodes |

### 3.4 批次追溯能力

| 候选 | collection_runs | pipeline_runs | trace_id | 增量模式 | 时间戳索引 |
|---|---|---|---|---|---|
| phase1 | 是（9+ 字段） | 是 | 是（new_trace_id） | 支持 (--incremental) | idx_run_time + 更多时间索引 |
| v0.2 | 是 | 是 | 否 | 支持 (--incremental) | idx_run_time |
| main | 是 | 否 | 否 | 否 | idx_run_time 仅 |
| delivery | 是 | 否 | 否 | 否 | idx_run_time 仅 |
| audit-hardening | 是 | 否 | 否 | 否 | idx_run_time 仅 |
| impl-tdd | 是 | 否 | 否 | 否 | idx_run_time 仅 |

### 3.5 导出能力

| 候选 | JSON 导出 | CSV 导出 | 导出入口 | 字段完整 | 编码 |
|---|---|---|---|---|---|
| phase1 | 是 | 是 | pipeline / CLI | 是 | UTF-8 |
| v0.2 | 是 | 是 | pipeline / CLI | 是 | UTF-8 |
| main | 否 | 否 | 无 | 无 | 无 |
| delivery | 否 | 否 | 无 | 无 | 无 |
| audit-hardening | 否 | 否 | 无 | 无 | 无 |
| impl-tdd | 否 | 否 | 无 | 无 | 无 |

### 3.6 APK/EXE 交付基础

| 候选 | Android 代码 | Windows 代码 | 打包脚本 | 跨平台核心解耦 |
|---|---|---|---|---|
| phase1 | 无 | 无 | 无 | 较好（pipeline.orchestrator） |
| v0.2 | 无 | 无 | 无 | 部分（pipeline 分离） |
| main | 无 | 无 | 无 | 无（main.py 耦合） |
| delivery | 无 | 无 | 无 | 无 |
| audit-hardening | 无 | 无 | 无 | 无 |
| impl-tdd | 无 | 无 | 无 | 无 |

**重要说明**：没有任何候选分支包含 Android APK 或 Windows EXE 的客户端代码。V0.3 需要新增客户端交付，创建客户端目录**不等于** APK/EXE 已经可交付，客户端构建与打包属于后续独立工作。

### 3.7 测试覆盖

| 候选 | 测试文件数 | 测试类型 | 说明 |
|---|---|---|---|
| phase1 | 31 | 审计 P0-P3 + 阶段 2-10 + Pipeline + 源 + 回放 | 最完整 |
| v0.2 | 16 | 纯函数 + 集成 + 失败恢复 | 有 ACCEPTANCE_V0.2.md |
| main | 0 | 无 | 零测试 |
| delivery | 3 | BB-D1 特定测试 | 极少 |
| audit-hardening | 4 | canonical_match_id / event pairing / replay pairing | 专项测试 |
| impl-tdd | 1 | test_line_bb_d1.py | 极少 |

### 3.8 已知缺陷（工作树与分支）

- **CONFLICT 与 IntegrityError 的混淆**：所有候选均存在，需明确区分。CONFLICT 是比赛匹配业务状态，IntegrityError 是 SQLite 数据库完整性约束异常。
- **save_mapping() 可能将已有 CID 更新为 NULL**：mapping/db.py 中 ON CONFLICT DO UPDATE 会无条件覆盖 canonical_match_id。
- **Unified 允许 NULL CID**：unified_snapshots.canonical_match_id 允许 NULL，需业务确认是否允许。
- **event_time=None 的业务处理**：所有候选均未最终确定。
- **CID 生成字段不完整**：make_canonical_id 仅用 home|away|event_time 分钟桶，存在同名球队同一分钟碰撞风险。
- **Unified superseded 后，下游失效传播不完整**：phase1 中 events/features 有 superseded 字段但传播链不完整。
- **Feature 全表 DELETE 与 cutoff 查询范围不一致**：phase1 features 引擎存在。
- **Replay V2 未过滤 superseded**：phase1 replay 存在。
- **Event 配对键未包含 source_market_id**：audit/bb-d1-event-pairing-20261027 已修复但需业务确认语义。

---

## 4. 评分矩阵（权重：V0.3 基础交付）

| 维度 | 权重 | phase1 | v0.2 | main | delivery | audit-hardening | impl-tdd |
|---|---:|---:|---:|---:|---:|---:|---:|
| 自动采集完整度 | 15% | 10 | 9 | 5 | 5 | 5 | 5 |
| RAW 保存完整度 | 15% | 10 | 8 | 6 | 6 | 6 | 6 |
| 数据库结构完整度 | 15% | 10 | 9 | 5 | 5 | 5 | 5 |
| 批次追溯 | 10% | 10 | 8 | 4 | 4 | 4 | 4 |
| 导出能力 | 10% | 10 | 9 | 0 | 0 | 0 | 0 |
| 测试覆盖 | 10% | 10 | 8 | 0 | 3 | 5 | 2 |
| 已知缺陷可控性 | 10% | 6 | 7 | 5 | 6 | 8 | 6 |
| 业务定义清晰度 | 10% | 7 | 8 | 5 | 7 | 8 | 7 |
| APK/EXE 就绪度 | 5% | 4 | 2 | 1 | 1 | 1 | 1 |
| **加权得分** | **100%** | **9.20** | **8.25** | **3.65** | **3.95** | **4.35** | **4.05** |

---

## 5. 结论

**唯一推荐基线：phase1 (`d39c7aa`)**

理由：
1. 功能最完整，覆盖 V0.3 所有基础交付项（采集、RAW、数据库、批次追溯、导出）并带有 31 个测试文件。
2. 提供统一 Pipeline Orchestrator，便于后续 V0.3 阶段化整理与客户端解耦。
3. 配置文件已填充（config_version v0.2, pipeline 0.2.0, schema_version 11），可直接作为 V0.3 配置基点。
4. 所有缺陷均可在 V0.3 整理阶段筛选修复，不存在“不可集成”的架构障碍。

**v0.2 作为参考基线**：适合作为导出功能和 ACCEPTANCE_V0.2.md 的参考，但缺少 trace_id 链路追踪和更完整的 RAW 账本。

**main 及 delivery/audit/impl-tdd**：仅适合作为修复补丁的来源，不适合作为 V0.3 基线（缺少导出、测试、完整数据库、RAW 账本等）。

---

## 6. 需从其他分支提取的有价值代码

| 来源 | 内容 | 用途 | 备注 |
|---|---|---|---|
| audit/bb-d1-event-pairing-20261027 | source_market_id 纳入事件配对键 | V0.3 映射层修复 | 需业务确认语义 |
| audit/bb-d1-canonical-match-id-20261029 | 从已匹配映射恢复 canonical_match_id | V0.3 映射层修复 | |
| audit/bb-d1-canonical-match-id-hardening-20261029 | 唯一约束 IntegrityError 仅捕获 | V0.3 数据库写入安全 | |
| delivery/bb-d1-p0-2-p0-3-20261029 | 跳过缺失盘口线的事件配对 | V0.3 采集链路防异常 | |
| impl-tdd | 负零 line 解析修复 | V0.3 采集数据清洗 | |
| v0.2 | ACCEPTANCE_V0.2.md、P2P RAW 同步语义、Monitor 异常保护 | V0.3 验收参考与 RAW 保护 | 仅作参考，不直接合并 |
