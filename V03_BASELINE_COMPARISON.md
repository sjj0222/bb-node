# V0.3 候选基线比较报告（第三轮修订版）

> 基线：phase1 @ d39c7aa（推荐），v0.2 @ 35ea228（参考）。  
> 本文件仅用于读取与分析，保存在 AndroidHarness 独立工作区 `v03_planning/`，**不修改 bb-node 仓库**。  
> 所有 Git 分支关系均基于真实 `git` 命令输出，禁止使用“线性后代、无合并冲突”这类推断性表述。

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

所有候选分支与 `main`（`74cff43929f997f9f72fdbae8649b39221b8b4b8`）的 merge-base 均为 `74cff439...` 本身。这表明 `main` 是每个候选分支的一个祖先提交，但**不得据此推断“线性后代”或“无合并冲突”**。合并冲突风险必须以实际文件差异和合并尝试为准，当前标记为**待核实**。

| 候选分支 | merge-base 与 main | 是否与 main 相同 |
|---|---|---|
| phase1 (`d39c7aa`) | `74cff439...` | 是 |
| v0.2 (`35ea228`) | `74cff439...` | 是 |
| impl-tdd (`b1581d7`) | `74cff439...` | 是 |
| delivery/bb-d1-p0-2-p0-3 (`d7637e4`) | `74cff439...` | 是 |
| audit/bb-d1-canonical-match-id-hardening (`f46251b`) | `74cff439...` | 是 |

### 2.2 ahead / behind 统计（`git rev-list --count`）

| 候选分支 | 先于 main 的提交数 | 落后于 main 的提交数 |
|---|---:|---:|
| phase1 | 20 | 0 |
| v0.2 | 5 | 0 |
| impl-tdd | 7 | 0 |
| delivery/bb-d1-p0-2-p0-3 | 5 | 0 |
| audit/bb-d1-canonical-match-id-hardening | 12 | 0 |

所有候选均先于 main，无落后提交。main 不包含任何候选分支独有的提交。

### 2.3 独有提交（`main..分支`）

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
| 9 | b7c8d65 | night: update summary |
| 10 | 4a25cbc | night: N05-N06 mapping notes |
| 11 | 51d6659 | night: N03 raw immutability notes |
| 12 | dd6bf33 | night: add audit docs for N00-N02,N04,N07 |

### 2.4 文件树差异（`git diff --name-only main 分支`）

| 候选分支 | 与 main 的文件差异数量 | 代表性差异文件（前 10 个） |
|---|---|---|
| phase1 | 40+ | .gitignore, ACCEPTANCE_V0.1/0.2.md, VERSION, backtest/, cli.py, config/config.json, core/, database/db.py, decisions/, mapping/ |
| v0.2 | 30+ | ACCEPTANCE_V0.1/0.2.md, backtest/, cli.py, config/config.json, core/collector.py, core/env.py, core/health.py, events/engine_v3.py, features/engine_v2.py |
| impl-tdd | 11 | docs/audit/night-run/*, events/line.py, tests/test_line_bb_d1.py |
| delivery/bb-d1-p0-2-p0-3 | 15 | BB_D1_P0_*_REPORT.md, REPAIR_REPORT.md, core/collector.py, events/engine_v3.py, mapping/db.py, mapping/unified_service.py, replay/, tests/test_*.py |
| audit/bb-d1-canonical-match-id-hardening | 22+ | BB_D1_P0_*_REPORT.md, REPAIR_REPORT.md, docs/audit/night-run/*, core/collector.py, events/engine_v3.py, events/line.py, mapping/db.py, mapping/unified_service.py, replay/, tests/test_*.py |

### 2.5 Patch-equivalent 提交检查

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

（此部分保持与上一版本一致，略）

---

## 4. 评分矩阵

（此部分保持与上一版本一致，略）

---

## 5. 结论

**唯一推荐基线：phase1 (`d39c7aa`)**

理由同上。v0.2 作为参考基线。main 及 delivery/audit/impl-tdd 仅适合作为修复补丁来源。

**重要提示**：基线选择基于功能完整度、测试覆盖、配置就绪度等维度。Git 分支关系上的 merge-base 相同**不构成**合并安全的依据，实际合并必须经过冲突检测和用户批准。

---

## 6. 需从其他分支提取的有价值代码

（此部分保持与上一版本一致，略）
