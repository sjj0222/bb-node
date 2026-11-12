# V0.3 第三轮修订变更日志

> 任务：根据第二轮审核意见，修订 `v03_planning/` 中 8 份 V0.3 规划报告。  
> 执行范围：仅修改 AndroidHarness 独立工作区 `v03_planning/` 内的 Markdown 报告。  
> **未修改 bb-node 主仓库任何文件，未执行任何 Git 操作、数据库操作或文件复制操作。**

---

## 1. 六项问题逐项修订结果

| 问题 | 状态 | 修订要点 |
|---|---|---|
| 问题 1：Git 分支关系判断 | 已修订 | 重写 `V03_BASELINE_COMPARISON.md` §2，基于真实 `git merge-base`、`git rev-list --count`、`git log`、`git diff --name-only` 输出，明确区分共同祖先、独有提交、ahead/behind、文件树差异、patch-equivalent 提交和实际合并冲突风险；删除“线性后代、无合并冲突”推断；不能确认的关系标记为“待核实” |
| 问题 2：APK/EXE 交付范围 | 已修订 | 统一 `V03_SCOPE.md`、`V03_TARGET_ARCHITECTURE.md`、`V03_ACCEPTANCE.md`、`V03_FINAL_RECOMMENDATION.md`：V0.3 只完成客户端架构规划、接口定义和必要目录预留，**不要求交付可安装 APK 或 EXE**；APK/EXE 实际交付移至后续阶段（V0.4+）；删除范围矛盾表述 |
| 问题 3：B1-B6 阻塞规则 | 已修订 | 统一 R1-R6；区分 B1-B4（待业务定义）与 B5/B6（代码安全问题）；明确 B1-B4 不阻塞基础采集和 RAW 保存，但未确认身份/盘口语义的数据不得作为已确认数据写入 Unified；B5/B6 必须在启用相关写入链路前修复并验收；明确基础采集、RAW 保存、映射、Unified 写入各自准入条件 |
| 问题 4：数据库 Schema 与迁移验证 | 已修订 | 明确 config.json schema_version 仅为配置声明；要求分别检查生产/审计附件/测试数据库真实结构；不得默认审计附件为生产主库；迁移脚本必须具备结构检测和兼容性判断；DB 文件 SHA256 仅用于备份完整性；未变更表规范化数据核验、变更表明确数据映射核验；哈希方案须覆盖普通表/WITHOUT ROWID/BLOB/NULL/视图/无稳定主键表；禁止未定义稳定排序时使用 ORDER BY rowid；WAL 备份必须用 online backup API 或明确停写+检查点；生产迁移需单独批准；未实现哈希方案标记为“待实现的设计要求” |
| 问题 5：客户端访问架构 | 已修订 | 统一核心服务运行于独立后台进程/服务器、核心服务为 SQLite 唯一写入方、客户端仅通过 API 访问、同设备部署也必须通过本地 API 或 IPC 不得以共享 SQLite 文件为默认方案；明确 Android/Windows 客户端数据目录；升级不覆盖用户数据；核心服务部署位置和 API 兼容策略列为架构决策项（待最终确定） |
| 问题 6：PR 与报告提交范围 | 已修订 | 在 `V03_FINAL_RECOMMENDATION.md` 中记录 aaa 分支混合提交范围（8 份规划报告 + 7 份 night-run 审计文件 + events/line.py 修改 + tests/test_line_bb_d1.py 新增）；提出后续文档 PR 建议文件范围；明确本次不修改代码、不创建/合并 PR、不创建新分支、不整理 Git 历史 |

---

## 2. 每份报告的修改摘要

| 报告 | 主要修改 |
|---|---|
| `V03_BASELINE_COMPARISON.md` | 重写 §2 Git 分支关系：基于真实命令输出的 merge-base、ahead/behind、独有提交列表、文件树差异、patch-equivalent 检查、合并冲突风险（待核实）；删除“线性后代、无合并冲突”表述 |
| `V03_SCOPE.md` | 修正 V0.3 交付目标（APK/EXE 改为架构规划，实际交付延期）；重写 §4 B1-B6：R1-R6 统一、B1-B4 与 B5/B6 分类、各链路准入条件明确；明确 B5/B6 必须在启用相关写入链路前修复并验收 |
| `V03_TARGET_ARCHITECTURE.md` | 统一客户端架构：核心服务独立运行且为 SQLite 唯一写入方；客户端仅通过 API 访问，同设备不得以共享 SQLite 为默认；明确客户端数据目录；增加架构决策项（部署位置、API 兼容策略）；明确 V0.3 不交付可安装 APK/EXE |
| `V03_DATA_MIGRATION_PLAN.md` | 明确 schema_version 仅为配置声明；要求分别检查三类数据库真实结构；迁移脚本必须具备结构检测和兼容性判断；DB 文件 SHA256 仅用于备份完整性；新增 §8 规范化数据核验设计要求（稳定排序、普通表/WITHOUT ROWID/BLOB/NULL/视图/无稳定主键表处理）；禁止未定义稳定排序时使用 ORDER BY rowid；WAL 备份限定为 online backup API 或停写+检查点；未实现方案标记为待实现 |
| `V03_CONSOLIDATION_STEPS.md` | 阶段 0 严格限定为只读资产盘点与备份可行性评估；阶段 4 增加结构检测、生产迁移单独批准、数据核验要求；阶段 6 明确为客户端架构规划（非 APK/EXE 交付）；阶段 2/3/7 增加 B5/B6 启用前修复验收要求；全程安全原则补充 B1-B6 准入规则 |
| `V03_ACCEPTANCE.md` | 客户端验收标准修正为架构规划/接口定义/C6 明确不交付 APK/EXE；B1-B6 验收重写为 R1-R6 分类表，B5/B6 未修复则阻塞相关写入链路启用；失败处理区分 B1-B4 与 B5/B6 |
| `V03_ROLLBACK_PLAN.md` | 与迁移方案对齐：DB 文件 SHA256 仅用于备份完整性；WAL 备份限定为 online backup API 或停写+检查点；阶段 4 预防措施增加结构检测和数据核验要求；禁止 rm -rf/reset main/直接覆盖原库等保持一致 |
| `V03_FINAL_RECOMMENDATION.md` | 汇总所有修订；记录 aaa 分支混合提交范围风险；提出后续文档 PR 建议文件范围；列出尚未解决的业务定义和技术决策；明确 V0.3 不交付可安装 APK/EXE |

---

## 3. 报告间一致性检查结果

| 检查项 | 结果 | 说明 |
|---|---|---|
| V0.3 范围一致性 | 通过 | 8 份报告均表述为：5 项基础交付 + 客户端架构规划（非 APK/EXE 交付）；APK/EXE 实际交付延期至 V0.4+ |
| B1-B6 与 R1-R6 一致性 | 通过 | Scope/Acceptance/Steps/Final 均采用 R1-R6；B1-B4 为待业务定义，B5/B6 为代码安全问题；各链路准入条件一致 |
| 阶段 0 只读性 | 通过 | Steps/Final/Rollback 均明确阶段 0 为只读资产盘点与备份可行性评估，未批准不执行冻结/备份/数据库操作 |
| 数据库路径和 Schema 版本描述 | 通过 | 三类数据库定义一致；schema_version 11 仅为配置声明；实际结构需阶段 0 只读确认 |
| WAL 备份策略 | 通过 | Migration/Steps/Rollback 均限定为 SQLite online backup API 或明确停写 + WAL 检查点 |
| 客户端 API 架构 | 通过 | Architecture/Scope/Acceptance/Final 均一致：核心服务独立运行且唯一写入方，客户端仅 API 访问，同设备不以共享 SQLite 为默认 |
| 回滚危险命令 | 通过 | 所有报告均禁止 rm -rf、reset main、直接覆盖原始数据库、删除 RAW/未提交文件 |
| 验收标准与交付范围匹配 | 通过 | 客户端验收为架构/接口/路径/升级策略/备份恢复设计，不含 APK/EXE 可安装交付 |
| 用户批准门槛 | 通过 | 阶段 0 单独批准、生产迁移单独批准、各阶段及阶段 8 需批准，在 Steps/Final/Rollback 中一致 |

---

## 4. 尚未解决的业务定义和技术决策

| 类别 | 项目 | 状态 |
|---|---|---|
| 业务定义 | B1: event_time=None 处理 | 待业务确认 |
| 业务定义 | B2: source_market_id 合并/隔离语义 | 待业务确认 |
| 业务定义 | B3: CID 生成字段扩展与碰撞处理 | 待业务确认 |
| 业务定义 | B4: Unified NULL CID 策略 | 待业务确认 |
| 代码安全 | B5: save_mapping NULL CID 覆盖修复 | 待修复并验收 |
| 代码安全 | B6: Collector CONFLICT/IntegrityError 区分 | 待修复并验收 |
| 架构决策 | 核心服务部署位置（同设备/局域网/远程） | 待最终确定 |
| 架构决策 | API 版本与兼容策略 | 待明确 |
| 技术实现 | 规范化数据核验哈希方案（含稳定排序、BLOB/NULL/WITHOUT ROWID/视图/无稳定主键表处理） | 待实现（设计要求已定义） |
| Git | aaa 分支混合提交整理方式 | 待用户决定 |

---

## 5. 本次未执行的操作清单

- 未修改 bb-node 主仓库任何文件
- 未修改数据库、RAW 文件或配置文件
- 未执行数据库迁移、备份复制、恢复或测试写操作
- 未执行 git commit、push、merge、rebase、reset、clean、checkout
- 未删除或修改任何分支、Tag 或 Git 历史
- 未创建或合并 PR
- 未修改 `events/line.py`、测试文件或其他代码
- 未将本次文档修订提交到 bb-node 主仓库
- 未执行阶段 0（只读资产盘点与备份可行性评估）

---

## 6. 当前 aaa 分支混合提交范围风险

`aaa` 分支相对 `main`（merge-base: `74cff439`）包含 9 个提交，文件变更混合了三类内容：

| 类别 | 文件/内容 |
|---|---|
| 规划文档 | `V03_ACCEPTANCE.md`, `V03_BASELINE_COMPARISON.md`, `V03_CONSOLIDATION_STEPS.md`, `V03_DATA_MIGRATION_PLAN.md`, `V03_FINAL_RECOMMENDATION.md`, `V03_ROLLBACK_PLAN.md`, `V03_SCOPE.md`, `V03_TARGET_ARCHITECTURE.md` |
| 审计文档 | `docs/audit/night-run/bb-d1-evidence-matrix.md`, `code-map.md`, `independent-review.md`, `normalized-contract.md`, `summary.md`, `task-status.json`, `test-baseline.md` |
| 代码修改 | `events/line.py`（修改）, `tests/test_line_bb_d1.py`（新增） |

**风险**：若直接基于 `aaa` 创建 PR，将同时引入代码变更和审计文件，超出规划文档修订范围。本次任务不执行任何 Git 操作，不整理该分支。

---

## 7. 后续建议的文档 PR 文件范围

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

## 8. 仍需用户批准的事项

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
