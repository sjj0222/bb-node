# 00_EXECUTIVE_SUMMARY.md

任务状态：**COMPLETE**

**是否修改了项目：NO。**
证据：正式项目 `git status --porcelain --ignored -uall` 仅显示 `?? devcopy/`（本轮之前既有）；`git rev-parse HEAD` = `74cff43`（未变）；49 个受跟踪文件 sha256 与任务前清单逐字节一致；本轮所有写操作都发生在 `devcopy/.harness_tmp/`（新建目录，属 devcopy 副本，非正式项目），未触碰正式项目任何文件、数据库、配置或 Git 元数据。

**是否执行测试：未执行测试套件（0 个测试运行）。**
原因（约束要求"若无法确认执行安全性，则只做静态审查"）：`main` 分支**无 `tests/` 目录**；上游 `origin/phase1` 的测试以 pytest 为依赖且 `origin/phase1` 树内含 `database/db.py`、`core/log.py` 等 **import 期即建库**的模块（`core/log.py:69 init()`），在无隔离副本的前提下运行有写 `~/bb_node/data/bb.db` 的风险。
替代验证：编写 **4 个只读 Python 脚本**（`devcopy/.harness_tmp/verify_*.py`，`PYTHONDONTWRITEBYTECODE=1`，cwd=`/tmp`），仅导入纯模块 `events.line`（不导入任何写库模块），用于计算边界值矩阵与 52 条真实迁移的混淆矩阵。退出码 0，输出见 `verify_*_output.txt`。
已运行命令的完整清单见 `07_RUN_LOG.md`。

---

## 最重要的 3 个发现

### 发现 1 —— 负零是唯一的根因，候选实现在真实数据上有 23% 分类错误
**【CODE + DATA + 实测】**
- `events/line.py:10-11` 用 `y = -abs(y) if x<0 else abs(y)` 决定第二腿符号，而 `float("-0")` = `-0.0`，`-0.0 < 0` 为 **False** → `"-0/0.5"` 的符号被翻转成正向。
- `"-0/0.5"` 在真实数据中出现 **342 次**（`ladder.txt`）+ 12 次（`ladder_v7.txt`）→ 占全部 3470 个盘口行的 9.9%（DATA）。
- 项目自有的 `origin/phase1:mapping/market.py:69-107 parse_line_quarters` 判 `"-0/0.5"` 为 `("-2:0", -1)`（负），**BB-D1 候选的 `value` 判为 `+0.25`**（正）→ 两者在最常见的分盘形态上**直接矛盾**。
- **实测 52 条真实迁移的混淆矩阵**（`verify_matrix_output.txt`）：规范口径下 28 条为跨盘、24 条为幅度变化；候选**跨盘识别 18/28（64%）、漏判 10 条、假判 2 条**，错误率 **12/52 = 23%**，且**全部**由负零引起。
- 候选相对 main 的净效果：跨盘识别 **0 → 18**，但新增 **2 条假跨盘**（首尔FC `'-0/0.5'→'-1.5'`）。两版在"是否产生事件"上都是 52/52，差别只在标签。

### 发现 2 —— "契约冲突"被高估；真正的风险是 `changed` 的取值集合发生变化
**【GIT + CODE】**
- `CROSS`/`SIGN_FLIP` 在 5 个分支、`git log --all -S` 全历史中 **0 命中**（Agent A + Agent D 独立确认）。
- 但**没有任何代码读取** `line_direction`/`line_change_type` 的字面值，DB 亦无 CHECK 约束 → **新增枚举不会破坏现有消费者**（Agent D CE6 纠正了主 Agent 前一轮的过强表述）。
- 真正的兼容性风险是：候选改变了 `changed` 的取值集合 → `LINE_CHANGE` **事件条数**变化 → `replay/event_v1.py` 的 `event_count`/`replay_hash` 变化 → 回放行**重新插入而非去重**（Agent D CE12）。
- 另：`steps` 在候选中存在**双量纲**（幅度分支 = 深度差，CROSS 分支 = 值差）；`devcopy/events/line.py:80` vs `:101`。

### 发现 3 —— 盘口字段在数据流中"不同源"，且事件配对用的是错的那个
**【CODE + GIT】**
- `sources/bb.py:40,43,46`：`line_raw` 取**选项级** `op.li`，`line` 取**盘口级** `mk.li` → 同一条记录两个值可能矛盾。上游提交 `af2db46`（P1-4「line 与 line_raw 层级矛盾…修复四分之一球盘被归错线」）已修，**main 仍缺**。
- `events/engine_v3.py:42` 用 **数值 `line`**（盘口级，且 `None` 被当 0）配对旧/新行，`:44-45` 却用 **`line_raw`**（选项级）判断是否变化 → 配对与比较使用**不同字段**。
- `events/engine_v3.py:33-35` 的分组键**不含 `market_id`**，而 `events_v3` 表（`:14-20`）**无 `market_id` 列** → 跨档位错配在下游**不可察觉**（DATA：真实数据中 market_id 会随档位轮播更换）。
- 下游另有两处断链：`features/engine_v1.py:7`/`engine_v2.py:9` `delete from features_v1/features_v2` 但**全仓库无 CREATE TABLE**；`core/status.py:3` 等读相对 `data/bb.db` 而写方用 `~/bb_node/data/bb.db`。

---

## BB-D1 是否建议进入修复阶段：**CONDITIONAL（可进入修复阶段，但不可按当前候选实现合并）**

**可以保留的结论**：符号翻转被漏报是**真实缺陷**（上游 `events/line.py` 与 main **逐字节相同**，即上游从未修复），候选"识别跨盘"的思路方向正确。

**必须先做的（阻塞合并）**：
1. 修复负零解析 —— 阶段 1（`05_FIX_PLAN.md`）
2. 停止自创 `value` 口径，改为复用项目自有的 `parse_line_quarters` 口径判等 —— 阶段 2
3. 用**独立 oracle**（`parse_line_quarters` 或手写真值表）替换现有"以实现自身为 oracle"的测试
4. `CROSS`/`SIGN_FLIP` 是否入规范需业务裁定（未决 U1）

**不可按当前候选合并的原因**：候选在真实数据上有 23% 分类错误、引入双量纲 `steps`、并与项目自有口径在最高频输入上矛盾。

---

## 仍未解决的问题（按阻塞程度排序）

1. **BLOCKER** — 负零解析（`events/line.py:10-11`）。当前所有解析器与候选实现都在最常见分盘形态上出错。
2. **BLOCKER** — 规范文件 `BBN-PRD-ARCH-SPEC V1.0`（§5.2 / §9-11 / §19 / 规则 7.1, 9.2, 39）**不在仓库任何分支**，因此"哪套口径是权威"**无法最终判定**（U6）。
3. **HIGH** — 跨盘是否需要独立事件类型（U1）；`steps` 统一单位（U3）；"同一盘口"按 `quarters` 还是 `mid` 判同（U2）。
4. **HIGH** — `line`/`line_raw` 同源改造会否让大量行变 `line=None`（Agent D CE13 测得 46.2%，**主 Agent 未独立复算**）→ 不能直接 cherry-pick `af2db46`（U4）。
5. **MEDIUM** — `canonical_match_id` 在生产链路是否恒为 NULL（HP-3 / U5）；`market_id` 轮播下的配对键设计（HP-2）。
6. **MEDIUM** — 原始 CSV（`~/odds_data/snapshots/*.csv`）不可访问 → **"等深异号翻转"在真实数据中出现 0 次**，BB-D1 的原始目标形态**无实证支撑**；需要含 `option_index`/`pe`/`received_at` 的完整快照才能确认。
7. **LOW** — `parse_line_quarters` 自身缺陷（银行家舍入、双符号未拒、`inf` 未捕获）需在复用前一并加固。

---

## 报告路径

`/data/data/com.androidharness.app/files/github-projects/bb-node-a6ff0096/devcopy/.harness_tmp/`

| 文件 | 内容 |
|---|---|
| `00_EXECUTIVE_SUMMARY.md` | 本文件 |
| `01_CANONICAL_LINE_SPEC.md` | 逐函数对照表 + 权威性判定 + 完整边界值矩阵 + 附录源码 |
| `02_EVENT_DATAFLOW.md` | 字段溯源表 + 10 条高风险数据路径 + CLEAN 清单 + 附录源码 |
| `03_TEST_AUDIT.md` | 测试资产盘点 + 23 例逐例分类 + 12 项盲区 + 最小补强建议 |
| `04_REAL_DATA_EVIDENCE.md` | 真实数据统计 + 52 条迁移混淆矩阵 + 覆盖范围与缺失数据 |
| `05_FIX_PLAN.md` | A–E 方案比较 + 5 阶段最小修复计划 + 验收标准 + 回滚 + 停止条件 |
| `06_AGENT_DISAGREEMENTS.md` | 4 个独立 Agent 的职责、分歧裁决、5 条新缺陷、6 项未决 |
| `07_RUN_LOG.md` | 时间线、实际命令、退出码、工具限制、安全检查 |
| `CHECKPOINT.md` | 阶段完成状态与续跑指令 |
| `verify_*.py` / `verify_*_output.txt` | 只读验证脚本与原始输出 |
| `boundary_test_*.txt`, `comparison_test.txt` | 边界值实测输出 |
| `agentC_test_audit.txt`, `agentD_adversarial.txt` | 独立 Agent 原始笔记 |

---

## 下一步建议（仅一个）

**先在 `devcopy/` 执行 `05_FIX_PLAN.md` 的阶段 1 + 阶段 2**：把负零解析与畸形输入处理修正，并把"同一盘口"判定统一到 `parse_line_quarters` 的 quarters/mid 口径，用 52 条真实迁移做独立 oracle 的全量回归；**在阶段 1–2 完成并通过回归之前，不要合并当前 BB-D1 候选，也不要引入 `CROSS`/`SIGN_FLIP`**。
