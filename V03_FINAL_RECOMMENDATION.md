# V0.3 最终建议报告

> 基线：phase1 (`d39c7aa`)。  
> 本报告汇总前七份报告，作为用户和 ChatGPT 审核的最终依据。  
> **本轮仅制定方案，不执行任何整理。**

---

## 1. 唯一推荐基线

**推荐：`phase1` (commit `d39c7aa`)**

---

## 2. 选择理由

| 维度 | phase1 | 理由 |
|---|---|---|
| 功能完整度 | 128 文件，31 测试 | 覆盖 V0.3 所有基础交付项，含采集、RAW、数据库、批次追溯、导出 |
| 自动采集能力 | Pipeline Orchestrator | 支持分阶段 COLLECT→NORMALIZE→MAPPING→UNIFIED，有 trace_id 链路追踪 |
| RAW 保存能力 | raw_records / raw_observations / unmapped_records | 最完整的 RAW 分层账本，支持内容哈希命名和幂等写入 |
| 数据库结构 | 39 表（审计附件 DB） | 完整的比赛、盘口、映射、统一、批次、分析表体系 |
| 批次追溯 | collection_runs + pipeline_runs + trace_id | 支持按批次查询历史，链路可追踪 |
| 导出能力 | JSON/CSV 导出 | V0.3 必须项，phase1 已具备 |
| 测试覆盖 | 31 个测试文件 | 审计 P0-P3 + 阶段 2-10 + Pipeline，可作为 V0.3 测试基点 |
| 配置就绪 | config.json 已填充 | config_version v0.2, schema_version 11, 源配置完整 |

**放弃其他候选的理由**：

- **v0.2**：功能完整但缺少 trace_id 链路追踪，RAW 账本不如 phase1 完整，适合作为次选和导出功能参考。
- **main**：仅 49 文件，零测试，无导出，空配置，仅适合作为修补来源。
- **delivery / audit-hardening / impl-tdd**：均为 main 的派生分支，专注 BB-D1 特定修复，缺少完整功能集，仅适合提取个别修复补丁。

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

**必须在 V0.3 中修复的缺陷**（阻塞项）：

1. **save_mapping() 不得将已有 CID 更新为 NULL**（mapping/db.py ON CONFLICT DO UPDATE 无条件覆盖）。
2. **Collector 必须拦截 CONFLICT**（写入层捕获 IntegrityError，避免重复写入异常）。
3. **Unified NULL CID 业务确认**（unified_snapshots.canonical_match_id 允许 NULL，需业务确认是否允许）。
4. **event_time=None 业务处理确认**（RAW 数据完整保存，不静默丢弃）。
5. **CID 生成字段扩展**（当前仅 home|away|event_time 分钟桶，存在碰撞风险，需业务确认后扩展字段）。

---

## 4. 哪些功能延期

| 功能 | 延期阶段 | 理由 |
|---|---|---|
| P2P 多节点同步 | V0.4+ | 需网络协议、节点发现、冲突解决，属高级架构 |
| Event / Feature / Signal | V0.4+ | 属分析模块，V0.3 仅需采集与落库 |
| Strategy / Decision | V0.5+ | 依赖 Signal，属业务决策层 |
| Replay / Backtest | V0.4+ | 依赖 Event/Feature，属历史回溯分析 |
| 高级盘口分析 | V0.5+ | 依赖完整事件与特征链路 |

---

## 5. 哪些业务定义尚未解决

| 序号 | 事项 | 现状 | V0.3 处理方式 |
|---|---|---|---|
| B1 | event_time=None 的业务处理 | 未最终确定 | 标记为待业务确认，RAW 完整保存，不静默丢弃 |
| B2 | source_market_id 合并或隔离 | 未确认 | 标记为待业务确认，不合并也不隔离，保留原始数据 |
| B3 | CID 生成字段不完整，碰撞风险 | 未确认 | 标记为待业务确认，RAW 完整保存，Unified 写入前需确认 |
| B4 | Unified 允许 NULL CID | 未确认 | 标记为待业务确认，NULL CID 记录不阻断采集 |
| B5 | save_mapping 可能覆盖 CID 为 NULL | 已发现 | 修复为仅在新 CID 不为 NULL 时更新 |
| B6 | Collector 漏拦截 CONFLICT | 已发现 | 修复为在写入层捕获 IntegrityError |

---

## 6. 最终目录结构

详见 `V03_TARGET_ARCHITECTURE.md` §2。核心变更：

- 新增 `database/migrations/` 独立管理迁移脚本。
- 新增 `export/` 目录承载 JSON/CSV 导出。
- 新增 `client/android/` 和 `client/windows/` 目录，与核心业务逻辑解耦。
- 新增 `scripts/backup.py` 和 `scripts/restore.py`。
- `pipeline/orchestrator.py` 简化为 COLLECT → NORMALIZE → MAPPING → UNIFIED，去除 Event/Feature/Strategy 等下游阶段。
- 保留 `mapping/` 中比赛映射与盘口映射分离。
- 保留 `data/raw/` 与数据库物理分离。

---

## 7. 历史数据迁移方案

详见 `V03_DATA_MIGRATION_PLAN.md`。核心要点：

1. 只读盘点所有数据库（`./data/bb.db`、审计附件 DB、测试 DB 等）和 RAW 文件（`data/raw/bb/`、`data/raw/ladder/` 等）。
2. 编写 `database/migrations/` 中的 001/002/003 迁移脚本。
3. 在数据库副本上测试迁移，验证行数、结构、SHA256 一致。
4. 生产库迁移前再次备份，迁移后再次校验。
5. 迁移失败时从备份恢复，见 `V03_ROLLBACK_PLAN.md` §6。
6. RAW 原始数据与标准化数据分层保存，RAW 不因标准化失败而丢弃。

---

## 8. 分阶段执行顺序

| 阶段 | 名称 | 是否需要用户批准 |
|---|---|---|
| 阶段 0 | 资产冻结与只读备份盘点 | 是 |
| 阶段 1 | 唯一基线确定（phase1） | 是 |
| 阶段 2 | 必要修复筛选 | 是 |
| 阶段 3 | 基础采集链路整理 | 是 |
| 阶段 4 | 数据库与 RAW 数据迁移 | 是（二次确认） |
| 阶段 5 | 导出功能 | 是 |
| 阶段 6 | Android APK / Windows EXE | 是 |
| 阶段 7 | 全链路验收 | 是 |
| 阶段 8 | 分支收敛到唯一 main | 是 |

详细执行内容见 `V03_CONSOLIDATION_STEPS.md`。

---

## 9. 每个阶段的验收标准

详见 `V03_ACCEPTANCE.md`。核心验收项：

- **数据**：RAW 不丢失、幂等性、批次追溯、映射状态明确、异常不静默丢弃、数据库重启可恢复。
- **导出**：JSON 正确、CSV 正确、字段完整、编码正确、可重复验证。
- **客户端**：Android 安装运行、Windows 安装运行、路径明确、升级不覆盖、备份恢复可用。
- **Git**：main 包含验收后代码、历史审计证据保存、远程只保留 main、工作区未提交内容妥善处理。

---

## 10. 回退与回滚

详见 `V03_ROLLBACK_PLAN.md`。关键回滚点：

- 阶段 4（数据库迁移）失败：从阶段 0 备份恢复数据库和 RAW 文件。
- 阶段 8（分支收敛）失败：重置 main 到合并前状态，从 archive/ 恢复误删代码。
- 任何阶段失败：暂停后续阶段，制定整改计划，重新验收。

---

## 11. 严格安全限制提醒

本轮**仅制定方案，不执行**。以下操作在本轮严格禁止：

- 修改任何 bb-node 文件
- 创建或删除 bb-node 文件
- 移动或覆盖文件
- 修改数据库
- 执行数据库迁移
- 运行可能产生写入的测试
- 创建、删除或修改 Git 分支
- commit、push、merge、rebase、reset、clean
- 覆盖工作区未提交修改

完成后只提交报告，等待用户和 ChatGPT 审核。

---

## 12. 输出文件清单

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

**下一步**：等待用户和 ChatGPT 对本方案的审核。审核通过后，方可进入阶段 0 执行。
