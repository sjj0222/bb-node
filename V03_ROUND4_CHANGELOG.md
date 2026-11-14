# V0.3 第四轮修订变更日志

> 任务：根据第三轮独立复核结果，对 V0.3 规划文件进行第四轮定点修订。  
> 执行范围：仅修改 AndroidHarness 独立工作区 `v03_planning/` 内的 Markdown 报告。  
> **未修改 bb-node 主仓库任何文件，未执行任何 Git 操作、数据库操作或文件复制操作。**

---

## 1. 六项问题逐项修订结果（第四轮）

| 问题 | 状态 | 修订要点 |
|---|---|---|
| R1：B2 未确认盘口数据的安全状态 | 已修订 | `V03_SCOPE.md` 新增 §4.4 B2 详细规则：RAW 原始数据完整保留、标准化记录可保留、未确认盘口映射标记为 "pending_review"、"pending_review" 不得写入 Unified、不得强行推断盘口含义、等待业务确认后再决定入 Unified；明确不决定 source_market_id 真实含义、线值等价性、主盘口识别、合并拆分规则 |
| R2：Unified 数据准入闸门 | 已修订 | `V03_TARGET_ARCHITECTURE.md` §5 数据流向图新增"身份与盘口语义准入检查"节点（B1-B6 对应），§8 统一备份恢复交付范围（方案与规范交付，工具不要求可执行） |
| R3：Schema 版本权威来源 | 已修订 | `V03_DATA_MIGRATION_PLAN.md` §3 新增：唯一权威记录位于数据库本身（PRAGMA user_version 或 schema_migrations 表），config.json 仅为配置声明；迁移与版本记录同事务；中断/失败时通过数据库内部版本识别实际版本；当前机制为待实现设计要求 |
| R4：备份恢复交付范围统一 | 已修订 | 统一 `V03_SCOPE.md`、`V03_TARGET_ARCHITECTURE.md` §8、`V03_ACCEPTANCE.md` C5：V0.3 交付备份恢复方案与操作规范（含目录结构、校验清单、回滚步骤、WAL 一致性备份方式），**不要求实际可执行工具**；验收条件为方案文档完整、流程清晰、可人工执行验证 |
| R5：回滚期间读写规则冲突 | 已修订 | `V03_ROLLBACK_PLAN.md` §5.2 分为两阶段：阶段一回滚执行（仅读操作与文件恢复，停止写入程序，不运行可能写数据库的程序，保留只读检查）；阶段二回滚后验证（独立步骤，需单独人工授权，未获授权不得启动可能写数据库的程序，真实读写验证不默认为回滚一部分） |
| R6：基线比较报告完整性 | 已修订 | `V03_BASELINE_COMPARISON.md` 恢复完整内容：§2 Git 分支关系（真实命令输出）、§3 功能维度详细对比（7 个子表）、§4 评分矩阵、§5 结论、§6 需提取代码、§7 证据来源与执行时间；删除"与上一版本一致，略"表述 |

---

## 2. 修正 GitHub 分支状态描述（R7）

| 文件 | 修正内容 |
|---|---|
| `V03_FINAL_RECOMMENDATION.md` §9 | 更新为：`main` HEAD `74cff439...`，`aaa` HEAD `93a2b5a`，ahead 10 commits，behind 0，19 个文件变化；标注此前 "9 commits / 17 files" 已过时 |
| `V03_ROUND3_CHANGELOG.md` | 新增注记：本日志记录第三轮时状态；当前 `aaa` 分支状态见 `V03_FINAL_RECOMMENDATION.md` §9 |
| `V03_ROUND3_REVIEW_REPORT.md` | 新增注记：本报告记录第三轮状态；当前状态见 `V03_FINAL_RECOMMENDATION.md` §9 |

---

## 3. 每份报告的修改摘要（第四轮）

| 报告 | 主要修改 |
|---|---|
| `V03_BASELINE_COMPARISON.md` | 恢复完整内容：§2 Git 分支关系（merge-base/ahead/behind/独有提交/文件差异/patch-equivalent/合并冲突风险）、§3 功能维度详细对比（7 子表）、§4 评分矩阵、§5 结论、§6 需提取代码、§7 证据来源与执行时间；删除"略"表述 |
| `V03_SCOPE.md` | §4.4 新增 B2 详细规则（6 条数据安全状态规则）；明确不决定 source_market_id 真实含义/线值等价/主盘口识别/合并拆分规则 |
| `V03_TARGET_ARCHITECTURE.md` | §5 数据流向图新增"身份与盘口语义准入检查"节点（B1-B6 对应）；§8 新增备份恢复交付范围统一定义（方案与规范交付，工具不要求可执行） |
| `V03_DATA_MIGRATION_PLAN.md` | §3 新增 Schema 版本权威来源：数据库本身（user_version/schema_migrations 表），config.json 仅配置声明；迁移与版本记录同事务；中断失败时通过数据库内部版本识别；当前机制为待实现设计要求 |
| `V03_CONSOLIDATION_STEPS.md` | 无实质修改（第三轮已满足第四轮要求） |
| `V03_ACCEPTANCE.md` | C5 修正为"V0.3 交付备份恢复方案与操作规范，不要求实际可执行工具"；失败处理区分 C5 确认方案文档完整性而非工具可执行性 |
| `V03_ROLLBACK_PLAN.md` | §5.2 回滚分两阶段：阶段一回滚执行（仅读操作与文件恢复，不运行写程序）；阶段二回滚后验证（独立步骤，需单独授权，不默认为回滚一部分） |
| `V03_FINAL_RECOMMENDATION.md` | §9 更新 GitHub 分支状态：main HEAD 74cff439...，aaa HEAD 93a2b5a，ahead 10，behind 0，19 文件变化；标注过时信息 |
| `V03_ROUND3_CHANGELOG.md` | 新增注记：记录第三轮时状态；当前状态见 V03_FINAL_RECOMMENDATION.md §9 |
| `V03_ROUND3_REVIEW_REPORT.md` | 新增注记：记录第三轮时状态；当前状态见 V03_FINAL_RECOMMENDATION.md §9 |

---

## 4. 报告间一致性检查结果（第四轮）

| 检查项 | 结果 | 说明 |
|---|---|---|
| V0.3 范围一致性 | 通过 | 8 份报告均表述为：5 项基础交付 + 客户端架构规划（非 APK/EXE 交付）；APK/EXE 实际交付延期至 V0.4+ |
| B1-B6 与 R1-R6 一致性 | 通过 | Scope/Acceptance/Steps/Final 均采用 R1-R6；B1-B4 为待业务定义，B5/B6 为代码安全问题；各链路准入条件一致 |
| 阶段 0 只读性 | 通过 | Steps/Final/Rollback/Changelog 均明确阶段 0 为只读资产盘点与备份可行性评估，未批准不执行 |
| 数据库分类与 Schema 版本描述 | 通过 | 三类数据库定义一致；schema_version 11 仅为配置声明；权威版本记录在数据库本身 |
| WAL 备份策略 | 通过 | Migration/Steps/Rollback 均限定为 SQLite online backup API 或明确停写 + WAL 检查点 |
| 客户端 API 架构 | 通过 | Architecture/Scope/Acceptance/Final 均一致：核心服务独立运行且唯一写入方，客户端仅 API 访问，同设备不以共享 SQLite 为默认 |
| 回滚安全 | 通过 | 所有报告均禁止 rm -rf、reset main、直接覆盖原库、删除 RAW/未提交文件；回滚分两阶段 |
| 验收标准与交付范围匹配 | 通过 | 客户端验收为架构/接口/路径/升级策略/备份恢复方案，不含 APK/EXE 可安装交付 |
| 用户批准门槛 | 通过 | 阶段 0 单独批准、生产迁移单独批准、各阶段及阶段 8 需批准，在 Steps/Final/Rollback 中一致 |
| GitHub 分支状态 | 通过 | V03_FINAL_RECOMMENDATION.md §9 / V03_ROUND3_CHANGELOG.md / V03_ROUND3_REVIEW_REPORT.md 均修正为 10 commits / 19 files / aaa HEAD 93a2b5a |

---

## 5. 尚未解决的业务定义和技术决策

| 类别 | 项目 | 状态 |
|---|---|---|
| 业务定义 | B1: event_time=None 处理 | 待业务确认 |
| 业务定义 | B2: source_market_id 合并/隔离语义 | 待业务确认 |
| 业务定义 | B3: CID 生成字段扩展与碰撞处理 | 待业务确认 |
| 业务定义 | B4: Unified NULL CID 策略 | 待业务确认 |
| 代码安全 | B5: save_mapping NULL CID 覆盖修复 | 待修复并验收 |
| 代码安全 | B6: Collector CONFLICT/IntegrityError 区分 | 待修复并验收 |
| 架构决策 | 核心服务部署位置 | 待最终确定 |
| 架构决策 | API 版本与兼容策略 | 待明确 |
| 技术实现 | 规范化数据核验哈希方案 | 待实现（设计要求已定义） |
| Git | aaa 分支混合提交整理方式 | 待用户决定 |

---

## 6. 本轮未执行的操作清单

- 未修改 bb-node 主仓库任何文件
- 未修改数据库、RAW 文件或配置文件
- 未执行数据库迁移、备份复制、恢复或测试写操作
- 未执行 git commit、push、merge、rebase、reset、clean、checkout
- 未删除或修改任何分支、Tag 或 Git 历史
- 未创建或合并 PR
- 未修改 `events/line.py`、测试文件或其他代码
- 未将本次文档修订提交到 bb-node 主仓库
- 未执行阶段 0

---

## 7. 当前 aaa 分支混合提交范围风险

当前 `aaa` 分支（最新 commit `93a2b5a`，基于 `b1581d7`，相对 `main` merge-base `74cff439`）包含：
- 规划文档：8 份 `V03_*.md`（第四轮修订版）
- 新增文档：`V03_ROUND3_CHANGELOG.md`、`V03_ROUND3_REVIEW_REPORT.md`
- 审计文档：7 份 `docs/audit/night-run/*`
- 代码修改：`events/line.py`（修改）、`tests/test_line_bb_d1.py`（新增）

**风险**：该混合范围不适合作为纯文档 PR 来源。本次未执行任何 Git 操作整理。

---

## 8. 后续建议的文档 PR 文件范围

建议后续单独创建文档 PR 时，仅包含：

- `V03_BASELINE_COMPARISON.md`
- `V03_SCOPE.md`
- `V03_TARGET_ARCHITECTURE.md`
- `V03_DATA_MIGRATION_PLAN.md`
- `V03_CONSOLIDATION_STEPS.md`
- `V03_ACCEPTANCE.md`
- `V03_ROLLBACK_PLAN.md`
- `V03_FINAL_RECOMMENDATION.md`

**不应包含**：`docs/audit/night-run/*`、`events/line.py`、`tests/test_line_bb_d1.py`、`v03_planning/*` 及任何代码文件。具体分支整理方式需用户单独批准。

---

## 9. 仍需用户批准的事项

| 事项 | 说明 |
|---|---|
| 阶段 0 执行 | 只读资产盘点与备份可行性评估需用户单独批准后方可执行；冻结/备份/数据库操作需另行单独批准 |
| 基线确定 | 确认 phase1 @ d39c7aa 为唯一推荐基线 |
| 修复筛选方案 | 确认 B5/B6 修复优先级及可选修复范围 |
| 生产迁移 | 数据库生产迁移必须单独获得用户批准 |
| 阶段 3-8 各阶段执行 | 各阶段执行前需用户批准 |
| aaa 分支整理 | 混合提交范围的整理方式需用户决定并批准 |
| B1-B4 业务定义 | 待业务方确认 |
| 核心服务部署位置与 API 兼容策略 | 待架构决策 |

---

## 10. 输出文件清单（第四轮新增/修订）

| 文件 | 说明 |
|---|---|
| V03_BASELINE_COMPARISON.md（第四轮修订） | 恢复完整内容，含证据来源表 |
| V03_SCOPE.md（第四轮修订） | 新增 B2 详细规则 |
| V03_TARGET_ARCHITECTURE.md（第四轮修订） | 新增 Unified 准入闸门、备份恢复交付范围 |
| V03_DATA_MIGRATION_PLAN.md（第四轮修订） | 新增 Schema 版本权威来源 |
| V03_CONSOLIDATION_STEPS.md（第三轮修订） | 无实质修改 |
| V03_ACCEPTANCE.md（第四轮修订） | C5 修正为方案文档交付，非工具可执行 |
| V03_ROLLBACK_PLAN.md（第四轮修订） | 回滚分两阶段，阶段二需单独授权 |
| V03_FINAL_RECOMMENDATION.md（第四轮修订） | 修正 GitHub 分支状态描述 |
| V03_ROUND3_CHANGELOG.md（修订） | 新增注记指向当前状态 |
| V03_ROUND3_REVIEW_REPORT.md（修订） | 新增注记指向当前状态 |
| V03_ROUND4_CHANGELOG.md | 第四轮变更日志（本文件） |
| V03_ROUND4_SELF_CHECK.md | 第四轮自检报告（见下） |

全部文件位于 AndroidHarness 独立工作区 `v03_planning/`，**未写入 bb-node 仓库**。
