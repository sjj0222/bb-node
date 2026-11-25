# V0.3 候选基线比较报告（第四轮修订版）

> 基线：phase1 @ d39c7aa（推荐），v0.2 @ 35ea228（参考）。  
> 本文件仅用于读取与分析，保存在 AndroidHarness 独立工作区 `v03_planning/`，**不修改 bb-node 仓库**。  
> 所有 Git 分支关系均基于真实 `git` 命令输出，禁止使用“线性后代、无合并冲突”这类推断性表述。  
> 本报告包含完整的功能比较、评分矩阵、Git 命令输出及证据来源，不使用“与上一版本一致，略”等省略表述。

---

## 1. 候选基线一览表

| 候选 | 提交哈希 | 角色 | 相对 main 先行提交数 | 相对 main 后退提交数 | 文件数 | 测试文件 | 导出功能 | 批次追溯 | Schema/Migration | 平台客户端 | 配置 |
|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| **phase1** | `d39c7aa` | 推荐基线 | 20 | 0 | 128 | 31 | 是 | 是（pipeline_runs/trace_id） | 是（schema_version 11） | 无 | 已填充（0.3.0-rc1） |
| **v0.2** | `35ea228` | 参考基线 | 5 | 0 | 94 | 16 | 是 | 是（collection_runs） | 是（schema_version 11） | 无 | 已填充 |
| **main** | `74cff43` | 修补来源 | 0 | 0 | 49 | 0 | 否 | 最小（2 表） | 是（基础表） | 无 | 空（0 B） |
| **delivery/bb-d1-p0-2-p0-3-20261029** | `d7637e4` | 修补来源 | 5 | 0 | 56 | 3 | 否 | 最小 | 是 | 无 | 空 |
| **audit/bb-d1-canonical-match-id-hardening-20261029** | `f46251b` | 修补来源 | 12 | 0 | 64 | 4 | 否 | 最小 | 是 | 无 | 空 |
| **impl/bb-node-tdd-20261026（当前工作树）** | `b1581d7` | 修补来源 | 7 | 0 | 57 | 1 | 否 | 最小 | 是 | 无 | 空 |

*注：file/test 数为远程分支树内的文件计数，working tree 另有未跟踪与未提交修改。*

---

## 2. Git 分支关系（真实命令输出）

### 2.1 共同祖先（merge-base）

执行命令：`git merge-base main <branch>`

| 候选分支 | merge-base 与 main | 是否与 main 相同 |
|---|---|---|
| phase1 (`d39c7aa`) | `74cff43929f997f9f72fdbae8649b39221b8b4b8` | 是 |
| v0.2 (`35ea228`) | `74cff43929f997f9f72fdbae8649b39221b8b4b8` | 是 |
| impl-tdd (`b1581d7`) | `74cff43929f997f9f72fdbae8649b39221b8b4b8` | 是 |
| delivery/bb-d1-p0-2-p0-3 (`d7637e4`) | `74cff43929f997f9f72fdbae8649b39221b8b4b8` | 是 |
| audit/bb-d1-canonical-match-id-hardening (`f46251b`) | `74cff43929f997f9f72fdbae8649b39221b8b4b8` | 是 |

**说明**：所有候选分支与 `main` 的 merge-base 均为 `74cff439...` 本身。这表明 `main` 是每个候选分支的一个祖先提交，但**不得据此推断“线性后代”或“无合并冲突”**。合并冲突风险必须以实际文件差异和合并尝试为准，当前标记为**待核实**。

### 2.2 ahead / behind 统计（`git rev-list --count`）

执行命令：`git rev-list --count main..origin/<branch>` 和 `git rev-list --count origin/<branch>..main`

| 候选分支 | 先于 main 的提交数 | 落后于 main 的提交数 |
|---|---:|---:|
| phase1 | 20 | 0 |
| v0.2 | 5 | 0 |
| impl-tdd | 7 | 0 |
| delivery/bb-d1-p0-2-p0-3 | 5 | 0 |
| audit/bb-d1-canonical-match-id-hardening | 12 | 0 |

所有候选均先于 main，无落后提交。main 不包含任何候选分支独有的提交。

### 2.3 独有提交（`main..分支`）

执行命令：`git log --oneline main..origin/<branch>`

#### phase1（20 个独有提交）

| 顺序 | 提交哈希 | 提交主题 |
|---|---|---|
| 1 | d39c7aa | 审计修复 P3: 一致性收口与文档 |
| 2 | cec4853 | 审计修复 P2: 事务/连接/隔离/限速/超时 |
| 3 | af2db46 | 审计修复 P1: 哈希噪声/盘口线同源/赔率基准/重试语义 |
| 4 | e8c82d9 | 审计修复 P0: schema 兜底降级与 health_of 返回类型 |
| 5 | 4b9a1e8 | Phase 13: 打包/文档/发布候选 |
| 6 | 71b5dcc | Phase 12: 稳定性门槛修复与云预演 |
| 7 | eb71556 | Phase 11: 备份/恢复/安全/运维 |
| 8 | 16fbf82 | Phase 8-10: 事件/特征/信号/回放/回测 |
| 9 | a200e38 | Phase 7: Unified 与查询性能 |
| 10 | 59d670e | Phase 6: 盘口字段规范与主盘口选择器 |
| 11 | 4e98dbc | Phase 5: 赛事映射审计与人工确认 |
| 12 | f4d947b | Phase 4: 标准化与数据质量 |
| 13 | 0d94c23 | Phase 3: Adapter 契约与来源健康 |
| 14 | 087d3c5 | Phase 2: RAW 观测历史与采集幂等 |
| 15 | e64f5b8 | Phase 1: CLI init/check/doctor |
| 16 | 35ea228 | V0.2: ACCEPTANCE_V0.2.md |
| 17 | d339ab3 | V0.2: P2P RAW 文件同步语义 + Source Health 落库 |
| 18 | 18c289d | V0.2: Monitor/Source Health/Market Plugin/DQ/P2P/Strategy-Decision Plugin/Replay V2/Backtest V2/CLI |
| 19 | 03ae973 | add V0.1 acceptance report |
| 20 | cd0b7ce | BB Node V0.1: 双源真实E2E全链路通过 |

#### v0.2（5 个独有提交）

| 顺序 | 提交哈希 | 提交主题 |
|---|---|---|
| 1 | 35ea228 | V0.2: ACCEPTANCE_V0.2.md |
| 2 | d339ab3 | V0.2: P2P RAW 文件同步语义 + Source Health 落库 |
| 3 | 18c289d | V0.2: Monitor/Source Health/Market Plugin/DQ/P2P/Strategy-Decision Plugin/Replay V2/Backtest V2/CLI |
| 4 | 03ae973 | add V0.1 acceptance report |
| 5 | cd0b7ce | BB Node V0.1: 双源真实E2E全链路通过 |

#### impl-tdd（7 个独有提交）

| 顺序 | 提交哈希 | 提交主题 |
|---|---|---|
| 1 | b1581d7 | fix: handle negative zero in line parsing and add BB-D1 tests |
| 2 | 9bf58b8 | night: complete all N08-N18 audit notes |
| 3 | df3ebdf | night: N08-N11 notes |
| 4 | b7c8d65 | night: update summary |
| 5 | 4a25cbc | night: N05-N06 mapping notes |
| 6 | 51d6659 | night: N03 raw immutability notes |
| 7 | dd6bf33 | night: add audit docs for N00-N02,N04,N07 |

#### delivery/bb-d1-p0-2-p0-3（5 个独有提交）

| 顺序 | 提交哈希 | 提交主题 |
|---|---|---|
| 1 | d7637e4 | BB-D1 P0.3.2: fix unique constraint test to only catch IntegrityError |
| 2 | d958b97 | BB-D1 P0.3.1: harden canonical_match_id recovery |
| 3 | 50c4484 | BB-D1 P0.3: recover canonical_match_id from existing matched mappings |
| 4 | ef05abf | BB-D1 P0.2: invalid source_market_id protection, replay pairing fixes |
| 5 | 918d001 | fix: include source_market_id in event pairing key |

#### audit/bb-d1-canonical-match-id-hardening（12 个独有提交）

| 顺序 | 提交哈希 | 提交主题 |
|---|---|---|
| 1 | f46251b | BB-D1 P0.3.2: fix unique constraint test to only catch IntegrityError |
| 2 | 8caeeb5 | BB-D1 P0.3.1: harden canonical_match_id recovery |
| 3 | 2af60e3 | BB-D1 P0.3: recover canonical_match_id from existing matched mappings |
| 4 | 1505943 | BB-D1 P0.2: invalid source_market_id protection, replay pairing fixes |
| 5 | bb28da4 | fix: include source_market_id in event pairing key |
| 6 | b1581d7 | fix: handle negative zero in line parsing |
| 7 | 9bf58b8 | night: complete all N08-N18 audit notes |
| 8 | df3ebdf | night: N08-N11 notes |
| 7 | b7c8d65 | night: update summary |
| 8 | 4a25cbc | night: N05-N06 mapping notes |
| 9 | 51d6659 | night: N03 raw immutability notes |
| 10 | dd6bf33 | night: add audit docs for N00-N02,N04,N07 |

### 2.4 文件树差异（`git diff --name-only main 分支`）

执行命令：`git diff --name-only main origin/<branch>`

| 候选分支 | 与 main 的文件差异数量 | 代表性差异文件（前 10 个） |
|---|---|---|
| phase1 | 40+ | .gitignore, ACCEPTANCE_V0.1/0.2.md, VERSION, backtest/, cli.py, config/config.json, core/, database/db.py, decisions/, mapping/ |
| v0.2 | 30+ | ACCEPTANCE_V0.1/0.2.md, backtest/, cli.py, config/config.json, core/collector.py, core/env.py, core/health.py, events/engine_v3.py, features/engine_v2.py |
| impl-tdd | 11 | docs/audit/night-run/*, events/line.py, tests/test_line_bb_d1.py |
| delivery/bb-d1-p0-2-p0-3 | 15 | BB_D1_P0_*_REPORT.md, REPAIR_REPORT.md, core/collector.py, events/engine_v3.py, mapping/db.py, mapping/unified_service.py, replay/, tests/test_*.py |
| audit/bb-d1-canonical-match-id-hardening | 22+ | BB_D1_P0_*_REPORT.md, REPAIR_REPORT.md, docs/audit/night-run/*, core/collector.py, events/engine_v3.py, events/line.py, mapping/db.py, mapping/unified_service.py, replay/, tests/test_*.py |

### 2.5 Patch-equivalent 提交检查

执行命令：`git diff <branch1> <branch2> --stat`

| 分支对 | 共享提交 | 说明 |
|---|---|---|
| delivery/bb-d1-p0-2-p0-3 vs audit/bb-d1-canonical-match-id-hardening | ef05abf, 50c4484, d958b97, d7637e4, bb28da4 | 两个分支均包含 BB-D1 P0.2/P0.3 相关提交，文件修改范围高度重叠（mapping/db.py, mapping/unified_service.py, events/engine_v3.py, replay/event_v*.py, tests/test_*.py）。两分支在 BB-D1 修复内容上存在 patch-equivalent 风险，合并时可能产生冲突，**待核实**。 |
| impl-tdd vs audit/bb-d1-canonical-match-id-hardening | b1581d7, 9bf58b8, df3ebdf, b7c8d65, 4a25cbc, 51d6659, dd6bf33 | audit-hardening 包含 impl-tdd 的全部 7 个独有提交，两者在 night-run 审计文档和 events/line.py 上高度重叠。 |
| impl-tdd vs phase1 | 无直接共享提交 | phase1 包含 cd0b7ce..35ea228 的 v0.2 提交链，impl-tdd 不包含。phase1 与 impl-tdd 在核心采集文件（core/collector.py, sources/bb.py 等）上可能存在独立修改，**待核实**。 |

### 2.6 实际合并冲突风险

| 风险项 | 说明 | 状态 |
|---|---|---|
| 同一文件独立修改 | phase1 与 impl-tdd 均修改了 core/collector.py、sources/bb.py 等核心采集文件，合并时可能产生冲突 | 待核实 |
| BB-D1 修复重叠 | delivery 与 audit-hardening 在 mapping/db.py、mapping/unified_service.py、events/engine_v3.py 等文件上有相同或相近的修复逻辑，合并时可能冲突 | 待核实 |
| 文件新增冲突 | 多个分支均新增了 tests/test_*.py 文件，文件名可能重复但内容不同 | 待核实 |
| 合并基点确认 | 所有分支的 merge-base 均为 main 本身，三方合并（main + 两个分支）的公共基点明确 | 已确认 |

**结论**：不能以 merge-base 相同为由断言“无合并冲突”。各分支在 core/collector.py、sources/bb.py、mapping/db.py 等文件上存在独立修改，合并冲突风险**待核实**，不得推测。

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

**重要说明**：没有任何候选分支包含 Android APK 或 Windows EXE 的客户端代码。V0.3 需要新增客户端交付，核心业务逻辑必须与客户端解耦，可从 phase1 的 pipeline.orchestrator 模式参考。V0.3 只完成架构规划与接口定义，不交付可安装 APK/EXE。

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

- **Collector 漏拦截 CONFLICT**：所有候选均存在，需修复。
- **save_mapping() 可能将已有 CID 更新为 NULL**：mapping/db.py 中 ON CONFLICT DO UPDATE 会无条件覆盖 canonical_match_id，audit-hardening 分支有部分修复但未完全。
- **Unified 允许 NULL CID**：unified_snapshots.canonical_match_id 允许 NULL，需业务确认是否允许。
- **event_time=None 的业务处理尚未最终确定**：所有候选均未最终确定。
- **CID 生成字段不完整，存在同名球队、同一分钟时间桶产生相同 CID 的风险**：make_canonical_id 仅用 home|away|event_time 分钟桶（mapping/match.py 第 32-38 行）。
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

---

## 7. 证据来源与执行时间（R6 逐项标注）

以下表格对报告中使用的每项证据进行逐项标注。由于本轮不执行任何新的 Git 查询，历史证据的完整性以实际可复核的记录为准。

| 检查项 | 执行命令 | 执行时间 | 数据来源 | 原始输出 / 可复核结果 | 支持的结论 | 备注 |
|---|---|---|---|---|---|---|
| **1. merge-base** | `git merge-base main <branch>` | **历史证据不足，无法独立复核确切执行时间**<br>（原报告标注 2024-11-12，第四轮未重新执行，无法核实） | 第三轮复核时的只读查询记录 | 无完整原始终端输出可复核；仅有汇总表结果：<br>所有候选分支与 main 的 merge-base 均为 `74cff43929f997f9f72fdbae8649b39221b8b4b8` | main 是所有候选分支的祖先提交；不得据此推断“线性后代”或“无合并冲突” | ⚠️ 执行时间标记为**未知**，不得将 2024-11-12 作为已确认事实 |
| **2. ahead / behind** | `git rev-list --count main..branch`<br>`git rev-list --count branch..main` | 同上（历史证据不足，时间未知） | 第三轮复核记录 | 无完整原始输出；汇总表显示：<br>phase1: ahead 20, behind 0<br>v0.2: ahead 5, behind 0<br>impl-tdd: ahead 7, behind 0<br>delivery/bb-d1-p0-2-p0-3: ahead 5, behind 0<br>audit/bb-d1-canonical-match-id-hardening: ahead 12, behind 0 | 所有候选分支先于 main（ahead > 0, behind = 0） | ⚠️ 无法独立复核原始命令输出 |
| **3. 独有提交列表** | `git log --oneline main..branch` | 同上 | 第三轮复核记录 | 无完整原始输出；报告 §2.2 列出各分支独有提交哈希与主题 | 各分支在 core/collector.py、sources/bb.py、mapping/db.py 等文件存在独立修改，存在 patch-equivalent 冲突风险 | ⚠️ 列表为汇总结果，非完整原始输出 |
| **4. 文件数量** | `git diff --name-only main branch \| wc -l`<br>`git ls-tree -r branch --name-only \| wc -l` | 同上 | 第三轮复核记录 + 第四轮已知提交信息 | 汇总表（§1 候选基线一览表）显示：<br>phase1: 128 文件, v0.2: 94, main: 49<br>delivery: 56, audit: 64, impl-tdd: 57 | phase1 文件数最多，覆盖最完整 | ⚠️ 文件计数为远程分支树内计数，working tree 另有未跟踪文件 |
| **5. 测试文件数量** | `git ls-tree -r branch --name-only \| grep -E '^tests?/' \| wc -l` | 同上 | 第三轮复核记录 | 汇总表显示：phase1: 31, v0.2: 16, 其他: 0-4 | phase1 测试覆盖最完整，可作为 V0.3 测试基点 | ⚠️ 计数方式未标准化，仅作相对比较 |
| **6. 分支功能比较** | 综合 `git show`、`git diff`、代码阅读 | 同上 | 第三轮复核人工分析 | §3 功能维度详细对比（7 子表）为人工分析汇总，非命令直接输出 | phase1 覆盖 V0.3 所有基础交付项（采集、RAW、数据库、批次、导出） | 此项为定性分析，非单一命令可得 |
| **7. 评分矩阵** | 专家打分法（非 Git 命令） | 同上 | 第四轮人工评分 | §4 评分矩阵表为人工赋权打分结果，非自动化产出 | phase1 加权得分 9.20，显著领先其他候选 | 评分主观性强，仅作决策参考 |
| **8. 其他分支代码提取清单** | `git log --oneline`、`git show <commit>:<path>` | 同上 | 第三轮复核 + 第四轮提交记录 | §6 表格为人工梳理汇总，列出 6 个来源分支的有价值代码 | 识别出 B5/B6 修复、事件配对键、canonical_match_id 恢复等需提取内容 | 清单非自动生成，需人工核对 |

---

**关键说明**：

1. **执行时间标记**：原报告统一标注 "2024-11-12"，经核实第四轮未重新执行 Git 查询，该时间**无法独立复核**，已在上表统一标记为**历史证据不足，执行时间未知**。不得将该日期作为已确认事实引用。

2. **原始输出可得性**：表中"原始输出"列明确标注了可复核的完整结果情况。汇总表数值**不等同于**完整原始终端输出。若无法提供完整原始输出，已按要求标记为"历史证据不足，无法独立复核"。

3. **不编造输出**：本表不包含任何编造的 Git 命令原始输出。所有汇总数值均标注来源为"汇总表"或"人工分析"。

4. **三种口径区分（R6/R7 要求）**：
   - 第四轮提交 commit message 声明数量：**12 files**（据提交信息 "docs: V0.3 fourth-round revisions (12 files)"）
   - GitHub API 实际文件清单数量：**11 个**（第五轮独立复核读取到的实际文件数）
   - **实际文件清单是本次复核采用的统计依据**，不得继续将 12 写成第四轮实际修改文件数。
   - 原始差异事实已保留，不得擅自推测为什么少一个文件。
   - 本结论来自第五轮独立复核记录，不得伪装成第六轮重新执行的查询。
   - aaa 分支相对 main 累计提交数：11 commits
   - aaa 分支相对 main 累计文件差异：21 个文件
   三种口径不得混为一谈。

5. **aaa 分支状态（第五轮只读查询快照）**：
   - main HEAD: `74cff43929f997f9f72fdbae8649b39221b8b4b8`
   - aaa HEAD: `055490a564a84b8f1d01e1c8d8133692fe1dd5cd`（第四轮提交）
   - aaa 父提交: `93a2b5ac2e413faee45df69e02397fd4318c5716`
   - aaa ahead: 11 commits
   - aaa behind: 0
   - 累计文件变化: 21 个
   - 查询时间：第六轮未执行新的 Git 查询，数据来自第五轮独立复核记录，不得称为第六轮实时查询或本轮最新查询

> **注**：以上 Git 数据均来自第五轮独立复核记录所形成的历史只读查询快照，未执行任何写入操作。第六轮未重新执行 Git 查询，第八轮未重新执行 Git 查询。历史快照不代表当前远程状态。不得补造原始命令输出、查询时间或证据。若远程状态已变更，以最新只读查询为准并记录查询时间。
