# V0.3 第五轮修订变更日志

> 任务：根据第四轮独立复核结果，对 V0.3 规划文件进行第五轮定点修订。  
> 执行范围：仅修改 AndroidHarness 独立工作区 `v03_planning/` 内的 Markdown 报告。  
> **未修改 bb-node 主仓库任何文件，未执行任何 Git 操作、数据库操作或文件复制操作。**

---

## 1. 五项问题逐项修订结果（第五轮）

| 问题 | 状态 | 修订要点 |
|---|---|---|
| **R1：B2 隔离存储与 Unified 准入语义** | 已修订 | `V03_SCOPE.md` §4.4 **明确选择方案 A**：未确认盘口映射的数据不进入正式 Unified 存储。7 条具体规则：RAW 完整保留、标准化记录可保留、Market Mapping 标记 "pending_review"、pending_review 数据进入独立待审核存储或现有表待审核区、**不写入 unified_snapshots**、**不参与正式 Unified 查询/统计/特征计算**、业务确认并经准入检查后才允许入 Unified。**修正 §4.4 重复编号**（原 4.、4. 改为 4.、5.、6.、7.）。`V03_TARGET_ARCHITECTURE.md` §5 准入规则同步体现方案 A。 |
| **R3：Schema 版本唯一权威来源** | 已修订 | `V03_DATA_MIGRATION_PLAN.md` §3 **确立 `PRAGMA user_version` 为唯一权威来源**：config.json schema_version 仅为配置声明；schema_migrations 表不作为第二个独立权威；迁移 DDL 与 user_version 更新同一事务；失败自动回滚版本不变；迁移前检查当前版本、迁移后验证结构与版本；标注当前代码无实现证据，为 V0.3 待实现设计要求。 |
| **R5：数据库与 RAW 恢复授权边界** | 已修订 | `V03_ROLLBACK_PLAN.md` §5.2 **阶段 4 回滚拆分为三个授权层次**：<br>**A 层（回滚前准备）**：停止写入程序、只读检查数据库/WAL/SHM/RAW、确认备份来源与磁盘空间，**严禁任何文件恢复或路径切换**。<br>**B 层（实际恢复操作）**：7 个子步骤（改名失败副本、恢复到新路径、只读验证、切换生产路径、恢复 RAW 到新路径、验证 RAW、切换 RAW 路径），**每项需单独人工授权**，不覆盖原始资产、使用新路径、保留失败副本、验证后再切换。<br>**C 层（恢复后验证）**：C1 只读检查无需额外授权；C2 真实读写验证**必须另行单独授权**，不作为默认回滚步骤。<br>**文档声明**：所有命令仅为操作方案示例，不构成执行授权。 |
| **R6：基线比较报告原始证据** | 已修订 | `V03_BASELINE_COMPARISON.md` §7 **证据表全面重写**：对 8 项证据逐项标注（命令、执行时间、数据来源、原始输出/可复核结果、支持结论、备注）。**原报告统一标注 "2024-11-12" 经核实无法独立复核，已统一标记为"历史证据不足，执行时间未知"**，不得将该日期作为已确认事实。明确**三种口径区分**：第四轮提交本身 12 文件 / aaa 累计 11 commits / aaa 累计 21 文件变化。给出最新只读查询结果（main HEAD、aaa HEAD、父提交、ahead/behind、文件数），记录查询时间原则。 |
| **R7：GitHub 分支状态更新** | 已修订 | 更新 `V03_FINAL_RECOMMENDATION.md` §9、`V03_ROUND4_CHANGELOG.md` §2/§4、`V03_ROUND4_SELF_CHECK.md` §2/§3/§5、`V03_BASELINE_COMPARISON.md` §7：<br>- main HEAD: `74cff43929f997f9f72fdbae8649b39221b8b4b8`（未因第四轮修改）<br>- aaa HEAD: `055490a564a84b8f1d01e1c8d8133692fe1dd5cd`（第四轮提交）<br>- aaa 父提交: `93a2b5ac2e413faee45df69e02397fd4318c5716`<br>- 第四轮提交信息: `docs: V0.3 fourth-round revisions (12 files)`<br>- aaa ahead: 11 commits，behind: 0<br>- 累计文件变化: 21 个<br>- **明确区分三种口径**，澄清 main 未修改、第四轮提交已入 aaa、aaa 含代码变更、未部署生产。<br>- 标注此前 "9/17"、"10/19"、"aaa HEAD 93a2b5a" 均已过时。 |

---

## 2. 每份报告的修改摘要（第五轮）

| 报告 | 主要修改 |
|---|---|
| `V03_SCOPE.md` | §4.4 明确选择方案 A，7 条规则编号连续（1-7），不再并列两种方案；标题更新为第五轮修订版 |
| `V03_TARGET_ARCHITECTURE.md` | §5 准入规则确认与方案 A 一致；标题更新为第五轮修订版 |
| `V03_DATA_MIGRATION_PLAN.md` | §3 确立 PRAGMA user_version 为唯一权威，标题更新为第五轮修订版 |
| `V03_ROLLBACK_PLAN.md` | 标题更新为第五轮修订版；文档声明命令仅为示例；§5.2 重构为 A/B/C 三层授权 |
| `V03_BASELINE_COMPARISON.md` | §7 证据表全面重写，8 项证据逐项标注，2024-11-12 时间标记为未知，三种口径区分，最新只读查询结果 |
| `V03_FINAL_RECOMMENDATION.md` | §9 全面更新 GitHub 分支状态，三种口径区分，关键澄清 |
| `V03_ROUND4_CHANGELOG.md` | §2 更新分支状态修正内容为第五轮版；§4 一致性检查更新分支状态行为第五轮版 |
| `V03_ROUND4_SELF_CHECK.md` | §2 R7 证据位置更新；§3 一致性检查更新分支状态；§4 证据缺口更新时间标记说明；§5 文件清单增加第五轮修订标记 |
| `V03_ROUND5_CHANGELOG.md` | **新增**（第五轮变更日志，本文件） |
| `V03_ROUND5_SELF_CHECK.md` | **新增**（第五轮自检报告） |

---

## 3. 报告间一致性检查结果（第五轮）

| 检查项 | 结果 | 说明 |
|---|---|---|
| V0.3 范围一致性 | 通过 | 8 份核心报告均表述为：5 项基础交付 + 客户端架构规划（非 APK/EXE 交付） |
| B1-B6 与 R1-R6 一致性 | 通过 | Scope/Acceptance/Steps/Final/Architecture/Migration/Rollback 均采用 R1-R6 定义；B1-B4 待业务定义，B5/B6 代码安全问题；各链路准入条件一致 |
| 阶段 0 只读性 | 通过 | Steps/Final/Rollback/Migration/Changelog/SelfCheck 均明确阶段 0 为只读资产盘点与备份可行性评估，未批准不执行 |
| 数据库分类与 Schema 版本描述 | 通过 | 三类数据库定义一致；schema_version 11 仅为配置声明；**唯一权威为 PRAGMA user_version**（R3 明确） |
| WAL 备份策略 | 通过 | Migration/Steps/Rollback 均限定为 SQLite online backup API 或明确停写 + WAL 检查点 |
| 客户端 API 架构 | 通过 | Architecture/Scope/Acceptance/Final 均一致：核心服务独立运行且唯一写入方，客户端仅 API 访问 |
| 回滚安全 | 通过 | 所有报告均禁止 rm -rf、reset main、直接覆盖原库、删除 RAW/未提交文件；**回滚分 A/B/C 三层授权**（R5 明确） |
| 验收标准与交付范围匹配 | 通过 | 客户端验收为架构/接口/路径/升级策略/备份恢复方案，不含 APK/EXE 可安装交付 |
| 用户批准门槛 | 通过 | 阶段 0 单独批准、生产迁移单独批准、各阶段及阶段 8 需批准，**B 层/C2 逐项/单独授权**（R5 明确） |
| GitHub 分支状态 | 通过（第五轮更新） | 所有引用文件均同步更新为：main HEAD 74cff439...，aaa HEAD 055490a...（第四轮提交），ahead 11，behind 0，累计 21 文件；明确三种口径 |
| B2 数据状态与准入语义 | 通过（R1 明确） | Scope §4.4 与 Architecture §5 均明确选择方案 A：pending_review 不入 Unified，不参与下游统计分析 |

---

## 4. 尚未解决的业务定义和技术决策

| 类别 | 项目 | 状态 | 说明 |
|---|---|---|---|
| 业务定义 | B1: event_time=None 处理 | 待业务确认 | 标记为待确认，不阻塞采集/RAW，阻塞未确认身份数据入 Unified |
| 业务定义 | B2: source_market_id 合并/隔离语义 | 待业务确认 | §4.4 定义了数据安全状态与准入语义，未决定业务含义 |
| 业务定义 | B3: CID 生成字段扩展与碰撞处理 | 待业务确认 | 标记为待确认 |
| 业务定义 | B4: Unified NULL CID 策略 | 待业务确认 | 标记为待确认 |
| 代码安全 | B5: save_mapping NULL CID 覆盖修复 | 待修复并验收 | 标记为启用映射写入链路前必须修复 |
| 代码安全 | B6: Collector CONFLICT/IntegrityError 区分 | 待修复并验收 | 标记为启用采集写入链路前必须修复 |
| 架构决策 | 核心服务部署位置 | 待最终确定 | 列为架构决策项 |
| 架构决策 | API 版本与兼容策略 | 待明确 | 列为架构决策项 |
| 技术实现 | 规范化数据核验哈希方案 | 待实现（设计要求已定义） | Migration §8.3 标记为设计要求，待实现 |
| 技术实现 | PRAGMA user_version 版本机制 | 待实现（设计要求已定义） | Migration §3 标记当前代码无实现证据，为 V0.3 待实现要求 |
| Git | aaa 分支混合提交整理方式 | 待用户决定 | 记录在 Final §9、Changelog §7 |

---

## 5. 证据缺口（第五轮更新）

1. **Git 命令历史执行时间**：原报告统一标注 "2024-11-12"，经第五轮核实无法独立复核，已在 `V03_BASELINE_COMPARISON.md` §7 明确标记为**历史证据不足，执行时间未知**；不得将该日期作为已确认事实引用。

2. **Schema 版本机制（user_version / schema_migrations 表）**：当前代码库中无实现证据，已在 `V03_DATA_MIGRATION_PLAN.md` §3 标记为**待实现设计要求**，不得声称已实现。

3. **规范化数据核验的稳定排序方式**（无稳定主键表的处理）：未实现，标记为待实现。

4. **aaa 分支最新远程状态**：本轮未执行新的只读查询，文档数据基于最近一次独立核查；如远程已变更，以最新只读查询为准并记录查询时间。

5. **原始终端输出完整性**：基线报告 §7 证据表中明确标注了各项证据的原始输出可得性；汇总表数值不等同于完整原始终端输出，无法提供完整原始输出的项已标记为"历史证据不足，无法独立复核"。

---

## 6. 所有修改文件的路径清单（第五轮）

| 文件 | 第四轮状态 | 第五轮修订 |
|---|---|---|
| v03_planning/V03_BASELINE_COMPARISON.md | 修订（恢复完整内容） | **修订（R6：证据表全面重写、时间标记、三种口径）** |
| v03_planning/V03_SCOPE.md | 修订（新增 B2 详细规则） | **修订（R1：明确方案 A、编号修正）** |
| v03_planning/V03_TARGET_ARCHITECTURE.md | 修订（新增准入闸门、备份恢复范围） | **修订（R1：准入规则与方案 A 一致）** |
| v03_planning/V03_DATA_MIGRATION_PLAN.md | 修订（新增 Schema 版本权威） | **修订（R3：PRAGMA user_version 为唯一权威）** |
| v03_planning/V03_CONSOLIDATION_STEPS.md | 无实质修改 | 无实质修改 |
| v03_planning/V03_ACCEPTANCE.md | 修订（C5 修正为方案文档交付） | 无实质修改 |
| v03_planning/V03_ROLLBACK_PLAN.md | 修订（回滚分两阶段） | **修订（R5：拆分 A/B/C 三层授权、示例声明）** |
| v03_planning/V03_FINAL_RECOMMENDATION.md | 修订（修正分支状态） | **修订（R7：全面更新分支状态、三种口径）** |
| v03_planning/V03_ROUND3_CHANGELOG.md | 修订（新增注记指向当前状态） | 无实质修改 |
| v03_planning/V03_ROUND3_REVIEW_REPORT.md | 修订（新增注记指向当前状态） | 无实质修改 |
| v03_planning/V03_ROUND4_CHANGELOG.md | 新增（第四轮变更日志） | **修订（R7：更新分支状态引用、一致性检查）** |
| v03_planning/V03_ROUND4_SELF_CHECK.md | 新增（第四轮自检报告） | **修订（R7：更新 R7 证据位置、一致性检查、证据缺口、文件清单）** |
| v03_planning/V03_ROUND5_CHANGELOG.md | — | **新增（第五轮变更日志，本文件）** |
| v03_planning/V03_ROUND5_SELF_CHECK.md | — | **新增（第五轮自检报告）** |

---

## 7. 完成标准确认

| 标准 | 是否满足 | 说明 |
|---|---|---|
| 五项遗留问题（R1/R3/R5/R6/R7）均已明确处理 | 是 | 逐项有修订对照表、证据位置 |
| 证据缺口如实披露 | 是 | §5 列出 5 项缺口，不遮掩不编造 |
| 文档相互一致 | 是 | §3 一致性检查 11 项全部通过 |
| 未触碰 BB-node 主仓库与任何数据 | 是 | 仅修改 v03_planning/ 内 Markdown 文档 |
| 未执行任何 Git 写操作、数据库操作、RAW 操作 | 是 | 纯文档修订 |
| 未创建 PR、未合并分支、未自动进入下一阶段 | 是 | 等待 ChatGPT 独立复核及用户明确授权 |

---

**完成状态**：第五轮文档修订和自检完成，**未获得阶段 0 执行授权**，更未获得冻结工作区、复制备份、数据库操作、代码修改、分支整合或 PR 合并授权。等待 ChatGPT 独立复核及用户明确授权。
