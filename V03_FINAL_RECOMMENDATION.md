# V0.3 最终建议报告（修订版）

> 基线：phase1 @ d39c7aa。  
> 本报告汇总前七份修订报告，作为 ChatGPT 二次审核的最终依据。  
> 保存在 AndroidHarness 独立工作区 `v03_planning/`，**不修改 bb-node 仓库**。

---

## 1. 唯一推荐基线

**推荐：`phase1` (commit `d39c7aa`)**

**参考基线：`v0.2` (commit `35ea228`)**，仅作为导出功能和 ACCEPTANCE_V0.2.md 的参考。

---

## 2. 选择理由

| 维度 | phase1 | 理由 |
|---|---|---|
| 功能完整度 | 128 文件，31 测试 | 覆盖 V0.3 所有基础交付项 |
| 自动采集能力 | Pipeline Orchestrator | 支持分阶段 COLLECT→NORMALIZE→MAPPING→UNIFIED，有 trace_id 链路追踪 |
| RAW 保存能力 | raw_records / raw_observations / unmapped_records | 最完整的 RAW 分层账本 |
| 数据库结构 | 39 表（审计附件 DB 推断） | 完整的比赛、盘口、映射、统一、批次表体系 |
| 批次追溯 | collection_runs + pipeline_runs + trace_id | 支持按批次查询历史 |
| 导出能力 | JSON/CSV 导出 | V0.3 必须项 |
| 测试覆盖 | 31 个测试文件 | 可作为 V0.3 测试基点 |
| 配置就绪 | config.json 已填充 | config_version v0.2, schema_version 11 |

**放弃其他候选的理由**：main 及 delivery/audit/impl-tdd 均为 main 的派生分支，缺少导出、测试、完整数据库、RAW 账本，仅适合作为修复补丁来源，不适合作为 V0.3 基线。

---

## 3. 哪些修复值得提取

| 来源 | 修复内容 | 优先级 | V0.3 处理 |
|---|---|---|---|
| audit/bb-d1-event-pairing-20261027 | source_market_id 纳入事件配对键 | 高 | 阶段 2 筛选，经业务确认后合并 |
| audit/bb-d1-canonical-match-id-20261029 | 从已匹配映射恢复 canonical_match_id | 高 | 阶段 2 筛选，合并 |
| audit/bb-d1-canonical-match-id-hardening-20261029 | 唯一约束 IntegrityError 仅捕获 | 高 | 阶段 2 筛选，合并 |
| delivery/bb-d1-p0-2-p0-3-20261029 | 跳过缺失盘口线的事件配对 | 中 | 阶段 2 筛选，合并 |
| impl-tdd (b1581d7) | 负零 line 解析修复 | 中 | 阶段 2 筛选，合并 |
| v0.2 | P2P RAW 同步语义、Monitor 异常保护 | 低 | 参考，V0.3 不实施 P2P |
| sources/bb.py（当前未提交修改） | save_raw raw_content 扩展、normalize 增强 | 中 | 阶段 2 经审计后决定是否合并，不得擅自覆盖 |

**必须在 V0.3 中修复的缺陷（阻塞项）**：

1. **save_mapping() 不得将已有 CID 更新为 NULL**（mapping/db.py ON CONFLICT DO UPDATE 无条件覆盖）。
2. **Collector 必须区分 CONFLICT（比赛匹配业务状态）与 IntegrityError（SQLite 数据库完整性约束异常）**，分别处理，不得用 IntegrityError 捕获代替业务状态判断。
3. **Unified NULL CID 业务确认**（unified_snapshots.canonical_match_id 允许 NULL，需业务确认是否允许）。
4. **event_time=None 业务处理确认**（RAW 数据完整保存，不静默丢弃）。
5. **CID 生成字段扩展**（当前仅 home\|away\|event_time 分钟桶，存在碰撞风险，需业务确认后扩展字段）。

---

## 4. 哪些功能延期

| 功能 | 延期阶段 | 理由 |
|---|---|---|
| P2P 多节点同步 | V0.4+ | 需网络协议、节点发现、冲突解决 |
| Event / Feature / Signal | V0.4+ | 属分析模块，V0.3 仅需采集与落库 |
| Strategy / Decision | V0.5+ | 依赖 Signal，属业务决策层 |
| Replay / Backtest | V0.4+ | 依赖 Event/Feature，属历史回溯分析 |
| 高级盘口分析 | V0.5+ | 依赖完整事件与特征链路 |
| Android APK / Windows EXE 实际交付 | 后续独立工作 | V0.3 阶段仅完成客户端架构规划和目录预留，**不交付可安装的 APK/EXE** |

---

## 5. 哪些业务定义尚未解决

| 序号 | 事项 | 现状 | V0.3 处理方式 |
|---|---|---|---|
| B1 | event_time=None 的业务处理 | 未最终确定 | 标记为待业务确认，RAW 完整保存，不静默丢弃 |
| B2 | source_market_id 合并或隔离 | 未确认 | 标记为待业务确认，不合并也不隔离，保留原始数据 |
| B3 | CID 生成字段不完整，碰撞风险 | 未确认 | 标记为待业务确认，RAW 完整保存，Unified 写入前需确认 |
| B4 | Unified 允许 NULL CID | 未确认 | 标记为待业务确认，NULL CID 记录不阻断采集 |
| B5 | save_mapping 可能覆盖 CID 为 NULL | 已发现 | 修复为仅在新 CID 不为 NULL 时更新 |
| B6 | Collector 漏拦截 CONFLICT | 已发现 | 区分 CONFLICT（业务状态）与 IntegrityError（数据库约束），分别处理 |

**统一阻塞规则（R1-R6）**：
- R1：原始采集和 RAW 保存可以继续。
- R2：未确认身份的数据不得被当作已确认比赛写入 Unified。
- R3：未确认盘口语义的数据不得被错误合并。
- R4：Unified 写入必须有明确的允许条件、隔离条件和状态记录。
- R5：异常记录不得被静默丢弃。
- R6：业务定义事项（B1-B6）必须在 V0.3 验收前明确标记状态，不得自行决策。

---

## 6. 最终目录结构

详见 `V03_TARGET_ARCHITECTURE.md` §2。核心变更：

- 新增 `database/migrations/` 独立管理迁移脚本。
- 新增 `export/` 目录承载 JSON/CSV 导出。
- 新增 `client/android/` 和 `client/windows/` 目录，**仅用于架构规划和接口预留，不等于 APK/EXE 可交付**。
- 新增 `scripts/backup.py` 和 `scripts/restore.py`。
- `pipeline/orchestrator.py` 简化为 COLLECT → NORMALIZE → MAPPING → UNIFIED，去除 Event/Feature/Strategy 等下游阶段。
- 保留 `mapping/` 中比赛映射与盘口映射分离。
- 保留 `data/raw/` 与数据库物理分离。

---

## 7. 客户端架构关键说明

| 问题 | 答案 |
|---|---|
| 核心采集服务运行在哪里 | 独立后台进程或服务器，不运行在客户端内 |
| Android 客户端如何访问 | 通过本地 API 或远程 API，不直接读写核心服务 SQLite 文件 |
| Windows 客户端如何访问 | 通过本地 API 或远程 API，不直接读写核心服务 SQLite 文件 |
| 是否采用本地 API | 是 |
| SQLite 文件由谁负责读写 | 核心服务进程负责所有读写，客户端仅通过 API 读取 |
| Android 沙盒与 Windows 数据目录 | 客户端私有目录，仅存储客户端缓存/配置/导出副本，不存储核心服务主数据库 |
| 升级不覆盖用户数据 | 升级仅替换程序文件，用户数据目录保留 |

---

## 8. 历史数据迁移方案

详见 `V03_DATA_MIGRATION_PLAN.md`。核心要点：

1. 三类数据库：生产数据库、`./data/bb.db`；审计附件数据库，`.harness/attachments/` 下 `.db` 文件；测试数据库，`./feature_test/data/bb.db` 等。**不得默认认定审计附件数据库为生产主数据库**。
2. Schema 版本：通过 `config/config.json`（schema_version 11）和 `database/db.py` 确认，V0.3 必须建立显式版本管理。
3. phase1 已有 RAW 账本与 `002_add_raw_ledger.sql`：使用 `CREATE TABLE IF NOT EXISTS` 避免重复建表。
4. SQLite WAL 一致性备份：使用 SQLite online backup API 或 `PRAGMA wal_checkpoint(TRUNCATE)` 后复制。
5. BLOB/WITHOUT ROWID 表/视图哈希处理：按主键顺序抽取行，BLOB 转十六进制字符串参与 JSON 序列化，视图仅校验 CREATE 语句文本。
6. 原始数据库文件哈希与迁移后文件哈希**不能要求相同**，迁移可能改变文件内部布局。
7. 未修改表做规范化数据哈希，变更表做明确的数据映射核验。
8. 迁移只在副本执行，生产迁移必须单独批准。

---

## 9. 分阶段执行顺序

| 阶段 | 名称 | 是否需要用户批准 |
|---|---|---|
| 阶段 0 | 资产冻结与只读备份盘点 | **是**（只读评估，未得到用户单独批准前不执行冻结/备份/数据库操作） |
| 阶段 1 | 唯一基线确定（phase1） | 是 |
| 阶段 2 | 必要修复筛选 | 是 |
| 阶段 3 | 基础采集链路整理 | 是 |
| 阶段 4 | 数据库与 RAW 数据迁移 | 是（生产迁移必须单独批准） |
| 阶段 5 | 导出功能 | 是 |
| 阶段 6 | Android APK / Windows EXE（架构规划） | 是 |
| 阶段 7 | 全链路验收 | 是 |
| 阶段 8 | 分支收敛到唯一 main | 是 |

详细执行内容见 `V03_CONSOLIDATION_STEPS.md`。

---

## 10. 每个阶段的验收标准

详见 `V03_ACCEPTANCE.md`。核心验收项：

- **数据**：RAW 不丢失、幂等性、批次追溯、映射状态明确、异常不静默丢弃、数据库重启可恢复。
- **导出**：JSON 正确、CSV 正确、字段完整、编码正确、可重复验证。
- **客户端**：架构解耦、路径明确、升级不覆盖用户数据、备份恢复可用（APK/EXE 实际交付延期）。
- **Git**：main 包含验收后代码、历史审计证据保存（通过 Tag/提交对象）、远程只保留 main、工作区未提交内容妥善处理。

---

## 11. 回退与回滚

详见 `V03_ROLLBACK_PLAN.md`。关键回滚原则：

- 不得默认执行 `rm -rf`。
- 不得默认 `reset main`。
- 不得直接覆盖原始数据库。
- 不得删除 RAW 或未提交工作区文件。
- 优先采用新目录、数据库副本、独立迁移目标、验证后切换路径、原始资产只读保留。
- Git 历史通过可恢复的提交对象和 Tag 保存，不得只复制代码文件就认为历史已经归档。

---

## 12. 严格安全限制提醒

本轮**仅修订规划文档，不执行任何整理**。以下操作严格禁止：

- 修改 bb-node 仓库任何文件
- 创建、删除、移动或覆盖 bb-node 文件
- 修改任何数据库
- 迁移 RAW
- 运行可能写入数据库的程序或测试
- 创建、删除或修改 Git 分支
- commit、push、merge、rebase、reset、clean
- 擅自修改用户未提交文件
- 执行阶段 0

---

## 13. 输出文件清单

| 文件 | 内容 | 路径 |
|---|---|---|
| V03_BASELINE_COMPARISON.md | 候选基线比较 | v03_planning/V03_BASELINE_COMPARISON.md |
| V03_SCOPE.md | 范围定义 | v03_planning/V03_SCOPE.md |
| V03_TARGET_ARCHITECTURE.md | 目标架构 | v03_planning/V03_TARGET_ARCHITECTURE.md |
| V03_DATA_MIGRATION_PLAN.md | 数据迁移方案 | v03_planning/V03_DATA_MIGRATION_PLAN.md |
| V03_CONSOLIDATION_STEPS.md | 实施阶段 | v03_planning/V03_CONSOLIDATION_STEPS.md |
| V03_ACCEPTANCE.md | 验收标准 | v03_planning/V03_ACCEPTANCE.md |
| V03_ROLLBACK_PLAN.md | 回滚计划 | v03_planning/V03_ROLLBACK_PLAN.md |
| V03_FINAL_RECOMMENDATION.md | 最终建议 | v03_planning/V03_FINAL_RECOMMENDATION.md |

全部文件位于 AndroidHarness 独立工作区 `v03_planning/`，**未写入 bb-node 仓库**。

---

**下一步**：等待 ChatGPT 对本修订方案的二次审核。审核通过后，方可进入阶段 0（且需用户单独批准后才执行冻结/备份/数据库操作）。
