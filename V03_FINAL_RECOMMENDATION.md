# V0.3 最终建议报告（第四轮修订版）

> 基线：phase1 @ d39c7aa。  
> 本报告汇总前七份第四轮修订报告，作为 ChatGPT 复核的最终依据。  
> 保存在 AndroidHarness 独立工作区 `v03_planning/`，**不修改 bb-node 仓库**。

---

## 1. 唯一推荐基线

**推荐：`phase1` (commit `d39c7aa`)**

**参考基线：`v0.2` (commit `35ea228`)**，仅作为导出功能和 ACCEPTANCE_V0.2.md 的参考。

**分支关系说明**：所有候选分支与 main 的 merge-base 均为 `74cff439`（main 本身），所有候选均先于 main（ahead 5-20, behind 0）。这**不构成**“线性后代、无合并冲突”的依据。各分支在 core/collector.py、sources/bb.py、mapping/db.py 等文件上存在独立修改和 patch-equivalent 风险，实际合并冲突风险**待核实**。详见 V03_BASELINE_COMPARISON.md §2。

---

## 2. 选择理由

| 维度 | phase1 | 理由 |
|---|---|---|
| 功能完整度 | 128 文件，31 测试 | 覆盖 V0.3 基础交付项 |
| 自动采集能力 | Pipeline Orchestrator | 分阶段采集，有 trace_id 链路追踪 |
| RAW 保存能力 | raw_records / raw_observations / unmapped_records | 最完整的 RAW 分层账本 |
| 批次追溯 | collection_runs + pipeline_runs + trace_id | 支持按批次查询历史 |
| 导出能力 | JSON/CSV 导出 | V0.3 必须项 |
| 测试覆盖 | 31 个测试文件 | 可作为 V0.3 测试基点 |
| 配置就绪 | config.json 已填充 | config_version v0.2, schema_version 11（配置声明，非实际 Schema 证明） |

---

## 3. V0.3 交付范围

### 3.1 必须交付

| 序号 | 功能 | 说明 |
|---|---|---|
| 1 | 自动采集 | 定时/手动从 BB Adapter 采集比赛与盘口数据 |
| 2 | RAW 原始数据完整保存 | 原始响应按内容哈希命名，分层保存，不覆盖，异常 RAW 不静默丢弃 |
| 3 | 正式数据库落库 | SQLite，匹配/盘口/快照/统一/映射/批次表 |
| 4 | 采集批次与历史追溯 | collection_runs 记录每次采集 |
| 5 | JSON/CSV 导出 | 导出比赛、盘口、快照、映射数据 |
| 6 | Android 客户端架构规划 | **仅架构规划、接口定义和必要目录预留，不交付可安装 APK** |
| 7 | Windows 客户端架构规划 | **仅架构规划、接口定义和必要目录预留，不交付可安装 EXE** |

**V0.3 不要求交付可安装的 APK 或 EXE。** 创建客户端目录不等于 APK/EXE 已可交付，客户端构建、签名、打包属于后续独立工作。

### 3.2 明确延期

| 功能 | 预计阶段 |
|---|---|
| Android APK 可安装交付 | V0.4+（后续独立工作） |
| Windows EXE 可安装交付 | V0.4+（后续独立工作） |
| P2P 多节点同步 | V0.4+ |
| Event / Feature / Signal | V0.4+ |
| Strategy / Decision | V0.5+ |
| Replay / Backtest | V0.4+ |
| 高级盘口分析 | V0.5+ |

---

## 4. B1-B6 处理方式与 R1-R6 阻塞规则

### 4.1 统一阻塞规则（R1-R6）

| 规则 | 说明 |
|---|---|
| R1 | 原始采集和 RAW 保存可以继续。 |
| R2 | 未确认身份的数据不得被当作已确认比赛写入 Unified。 |
| R3 | 未确认盘口语义的数据不得被错误合并。 |
| R4 | Unified 写入必须具有明确的允许条件、隔离条件和状态记录。 |
| R5 | 异常记录不得被静默丢弃。 |
| R6 | B1-B6 必须在 V0.3 验收前明确标记为待业务确认或已修复，不得擅自决定业务定义。 |

### 4.2 B1-B6 分类

| 序号 | 事项 | 类型 | 处理方式 | 准入影响 |
|---|---|---|---|---|
| B1 | `event_time=None` 的业务处理 | 待业务定义 | 标记待确认，RAW 完整保存 | 不阻塞采集/RAW；阻塞未确认身份数据写入 Unified |
| B2 | `source_market_id` 合并或隔离语义 | 待业务定义 | 标记待确认，不合并不隔离，保留原始数据 | 不阻塞采集/RAW；阻塞未确认盘口语义的错误合并 |
| B3 | CID 生成字段不完整，碰撞风险 | 待业务定义 | 标记待确认，RAW 完整保存 | 不阻塞采集/RAW；阻塞未确认身份数据写入 Unified |
| B4 | Unified 允许 NULL CID | 待业务定义 | 标记待确认，需明确隔离条件和状态记录 | 不阻塞采集/RAW；阻塞 NULL CID 作为已确认比赛进入 Unified |
| B5 | `save_mapping()` 可能将已有 CID 更新为 NULL | 代码安全问题 | **必须在启用映射写入链路前修复并验收** | 未修复则阻塞映射写入链路启用 |
| B6 | Collector 未区分 CONFLICT/IntegrityError | 代码安全问题 | **必须在启用采集写入链路前修复并验收** | 未修复则阻塞采集写入链路启用 |

**明确**：B1-B4 未解决不阻塞基础采集和 RAW 保存，但**不得**将未确认数据作为已确认数据写入 Unified。B5、B6 必须修复并验收后才能启用相关写入链路。

---

## 5. 客户端架构

| 项目 | 结论 |
|---|---|
| 核心采集服务运行位置 | 独立后台进程或服务器（具体部署位置为**架构决策项，待最终确定**） |
| SQLite 主数据库唯一写入方 | 核心服务进程 |
| 客户端访问方式 | Android/Windows 客户端通过 API 访问；同设备部署也必须通过本地 API 或明确的进程间接口，**不得以共享 SQLite 文件作为默认方案** |
| 客户端数据目录 | Android：应用私有目录；Windows：`%APPDATA%\BB-Node\` 或用户文档目录（仅缓存/配置/导出副本） |
| 升级策略 | 仅替换程序文件，不覆盖用户数据 |
| 版本/API 兼容策略 | **架构决策项，待明确**（API 版本、兼容矩阵、降级策略、格式版本） |

---

## 6. 数据库与迁移

| 项目 | 结论 |
|---|---|
| 三类数据库 | 生产数据库 / 审计附件数据库 / 测试数据库，**不得默认认定审计附件数据库为生产主数据库** |
| Schema 版本 | `config/config.json` 中 `schema_version: 11` **仅为配置声明**，不能证明所有数据库实际 Schema 均为 11；各数据库实际结构需在阶段 0 只读确认。**Schema 版本唯一权威记录位于数据库本身（PRAGMA user_version 或 schema_migrations 表），config.json 仅为配置声明** |
| 迁移脚本 | 必须具备结构检测和兼容性判断，不能只依赖 `CREATE TABLE IF NOT EXISTS` |
| WAL 备份 | 必须使用 SQLite online backup API 或明确停写 + WAL 检查点流程 |
| 数据库文件 SHA256 | **仅用于备份文件完整性验证**，不作为迁移前后数据库相同的判断标准 |
| 数据核验 | 未变更表规范化数据核验；变更表明确的数据映射核验；哈希方案须处理普通表、WITHOUT ROWID 表、BLOB、NULL、视图、无稳定主键的表；不得在未定义稳定排序方式时直接使用 `ORDER BY rowid`；**尚未实现可执行代码，标记为待实现的设计要求** |
| 生产迁移 | 仅在副本执行测试，**生产迁移必须单独获得用户批准** |

---

## 7. 回滚原则

- 不得默认执行 `rm -rf`、`reset main`
- 不得直接覆盖原始数据库，不得删除 RAW 或未提交工作区文件
- 优先采用新目录、数据库副本、独立迁移目标、验证后切换路径、原始资产只读保留
- Git 历史通过可恢复的提交对象和 Tag 保存，不得只复制代码文件就认为历史已经归档
- 回滚分为两阶段：阶段一回滚执行（仅读操作与文件恢复），阶段二回滚后验证（需单独人工授权，不默认作为回滚一部分）

---

## 8. 分阶段执行顺序

| 阶段 | 名称 | 用户批准 |
|---|---|---|
| 阶段 0 | 只读资产盘点与备份可行性评估 | **是**（未批准前不执行冻结/备份/数据库操作） |
| 阶段 1 | 唯一基线确定（phase1） | 是 |
| 阶段 2 | 必要修复筛选 | 是 |
| 阶段 3 | 基础采集链路整理 | 是 |
| 阶段 4 | 数据库与 RAW 数据迁移 | 是（生产迁移单独批准） |
| 阶段 5 | 导出功能 | 是 |
| 阶段 6 | Android/Windows 客户端架构规划 | 是 |
| 阶段 7 | 全链路验收 | 是 |
| 阶段 8 | 分支收敛到唯一 main | 是 |

阶段 0 **严格限定为只读**，详见 V03_CONSOLIDATION_STEPS.md。

---

## 9. 当前 GitHub 分支状态（第四轮修订）

| 项目 | 状态 | 说明 |
|---|---|---|
| 比较基准 | `main...aaa` | - |
| `main` HEAD | `74cff43929f997f9f72fdbae8649b39221b8b4b8` | 未修改 |
| `aaa` HEAD | `93a2b5a` (短 SHA) | - |
| `aaa` ahead | 10 commits | 相对于 `main` |
| `aaa` behind | 0 | 相对于 `main` |
| 文件变化 | 19 个文件 | 8 份规划报告 + 2 份新增文档 + 审计文档 + 代码修改 |
| 规划报告 | 8 份 V03_*.md | 已修订至第四轮 |
| 新增文档 | V03_ROUND3_CHANGELOG.md, V03_ROUND3_REVIEW_REPORT.md | 第三轮产出 |
| 审计文档 | 7 份 docs/audit/night-run/* | 来自第三轮提交 |
| 代码修改 | events/line.py, tests/test_line_bb_d1.py | 来自第三轮提交 |

**说明**：此前报告中出现的 "9 commits / 17 files" 已过时，不得继续沿用。当前 `aaa` 分支已包含上述全部变更。**不能表述成整个 GitHub 仓库完全没有变化**，也不得将分支文件变更误写为生产环境已经部署。

---

## 10. 尚未解决的业务定义和技术决策

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

## 11. 输出文件清单

| 文件 | 内容 | 路径 |
|---|---|---|
| V03_BASELINE_COMPARISON.md | 候选基线比较（第四轮修订） | v03_planning/V03_BASELINE_COMPARISON.md |
| V03_SCOPE.md | 范围定义（第四轮修订） | v03_planning/V03_SCOPE.md |
| V03_TARGET_ARCHITECTURE.md | 目标架构（第四轮修订） | v03_planning/V03_TARGET_ARCHITECTURE.md |
| V03_DATA_MIGRATION_PLAN.md | 数据迁移方案（第四轮修订） | v03_planning/V03_DATA_MIGRATION_PLAN.md |
| V03_CONSOLIDATION_STEPS.md | 实施阶段（第三轮修订） | v03_planning/V03_CONSOLIDATION_STEPS.md |
| V03_ACCEPTANCE.md | 验收标准（第四轮修订） | v03_planning/V03_ACCEPTANCE.md |
| V03_ROLLBACK_PLAN.md | 回滚计划（第四轮修订） | v03_planning/V03_ROLLBACK_PLAN.md |
| V03_FINAL_RECOMMENDATION.md | 最终建议（第四轮修订） | v03_planning/V03_FINAL_RECOMMENDATION.md |
| V03_ROUND3_CHANGELOG.md | 第三轮变更日志 | v03_planning/V03_ROUND3_CHANGELOG.md |
| V03_ROUND3_REVIEW_REPORT.md | 第三轮复核报告 | v03_planning/V03_ROUND3_REVIEW_REPORT.md |
| V03_ROUND4_CHANGELOG.md | 第四轮变更日志 | v03_planning/V03_ROUND4_CHANGELOG.md |
| V03_ROUND4_SELF_CHECK.md | 第四轮自检报告 | v03_planning/V03_ROUND4_SELF_CHECK.md |

全部文件位于 AndroidHarness 独立工作区 `v03_planning/`，**未写入 bb-node 仓库**。

---

**下一步**：等待 ChatGPT 复核。审核通过后，方可进入阶段 0（且需用户单独批准后才执行任何只读盘点动作；冻结/备份/数据库操作需另行单独批准）。
