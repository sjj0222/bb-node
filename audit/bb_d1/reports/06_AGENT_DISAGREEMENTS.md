# 06_AGENT_DISAGREEMENTS.md

> 本轮**实际启动了 4 个独立 Agent**（A/B/C/D，均为只读子 Agent，共享同一仓库但各自独立取证），主 Agent 汇总并裁决。
> 各 Agent 的原始输出见：`devcopy/.harness_tmp/agentC_test_audit.txt`、`devcopy/.harness_tmp/agentD_adversarial.txt`。
> 主 Agent 对所有关键数字做了**独立复算**（`verify_claims.py` / `verify_matrix.py` / `verify_boundary.py`）。

---

## 1. 各 Agent 职责与独立取证方式

| Agent | 职责 | 独立取证手段 | 主要产出 |
|---|---|---|---|
| A | 盘口规范 + Git 历史 | `git log --diff-filter=A`、`git log --all -S`、`git show`、5 分支 `git grep` | 权威性判定、逐函数表、契约原文 |
| B | 源→事件数据流 | 逐文件通读 + 纯函数模拟 | 10 条高风险路径 + CLEAN 清单 |
| C | 测试质量/边界 | 逐测试分类 + 变异存活实验 | 23 例分类 + 12 项盲区 |
| D | **反方** | 对 5 条既有结论逐条攻击 + 自建 9 个脚本 | 13 条反例、3 条最弱结论、4 条新缺陷 |

**独立性保证**：A/B/C/D 各自独立取证，均未看到主 Agent 的中间结论；D 的任务书明确要求"假设结论可能错误"。

---

## 2. 分歧一：`parse_line_quarters` 是否为权威规范？

| 主张方 | 主张 | 证据 |
|---|---|---|
| 主 Agent（前一轮报告） | 是"项目自有的权威规范（规格 §5.2）" | `origin/phase1:mapping/market.py:70` docstring 自称；`tests/test_phase6.py:23` 有 R1 回归测试 |
| **Agent A** | **否（最多 PARTIAL）** | 规格文件**不在任何分支**（5 分支 `ls-tree` 无 spec 文件；`git log --all -S'BBN-PRD-ARCH-SPEC'` 仅命中 `docs/RELEASE_NOTES.md:5` 的一句引用）；`parse_line_quarters` 只被**映射层**（`mapping/market.py:160`、`quality/validator.py:96`）调用；**事件链路从未采用**：`origin/phase1:events/engine_v3.py:34,53` 仍 `from events.line import compare_line`，且 `git diff main origin/phase1 -- events/line.py` **为空**；它比 `events/line.py` **晚 6 周**出现（`59d670e`, 2026-10-21 vs `f993b8c`, 2026-09-05） |
| **Agent D（CE1）** | 同意 A，并加强：这是**不同子系统**的规范（市场映射），与"盘口变化分类"无关 | `git show main:mapping/market.py \| grep -c parse_line_quarters` → 0；spec 文档 40 处代码引用但文件不在 tree |

**裁决：Agent A / D 的证据更强。** 主 Agent 前一轮的"权威规范"表述**过强**，已在本轮全部交付物中更正为：
> `parse_line_quarters` 是**上游映射层**的规范化实现，带 R1 回归测试，但**不能**认定为盘口变化分类的权威规范；规格 §5.2 原文不可核实（**UNKNOWN**）。

**保留的共同点**：它仍是**唯一有测试固化的负零正确口径**（`test_phase6.py:23-28`），因此仍是修复阶段 1–2 的**最佳参照实现**，只是其"权威性"未获证实。

---

## 3. 分歧二："CROSS/SIGN_FLIP 与既有契约冲突"的严重程度

| 主张方 | 主张 | 证据 |
|---|---|---|
| 主 Agent（前一轮） | 与既有契约**不兼容**，属"中"严重性 | `origin/phase1:tests/test_line.py:3-6` 固定枚举；全历史 0 命中 |
| **Agent D（CE6）** | "字符串事实为真，但**契约冲突被夸大**" | `git log --all -S'CROSS'`/`-S'SIGN_FLIP'` 全空（事实成立）；但 `git grep -in "select.*line_direction|where.*line_direction|group by.*line_direction" $(git rev-list --all)` → **空**；DB 无 CHECK 约束 → **无任何消费者读取该字面值** → 新增枚举**不会**破坏现有代码 |
| Agent C | 真正的冲突在 `changed` 语义与 `steps` 量纲，不在词表 | 与 D 一致 |

**裁决：D 的证据更强，冲突等级应从"中"降为"低"（仅文档/语义层面）。**
但 D 同时指出**被低估的真风险**（见 §5 ND/CE7、CE12）：候选**改变了 `changed` 的取值集合** → `LINE_CHANGE` 事件**条数**变化 → `replay/event_v1.py` 的 `event_count`/`replay_hash` 变化 → 回放行重新插入而非去重。主 Agent 前一轮**遗漏**了这一点。

---

## 4. 分歧三：负零缺陷的影响面（本次最重要的修正）

| 主张方 | 主张 | 证据 |
|---|---|---|
| **Agent D（ND1）** | main 与候选**都漏掉 28 条规范跨盘中的 10 条**，并**产生 2 条假跨盘**；根因是 `-0` | 52 条真实迁移逐条比对 |
| **主 Agent 复算** | **部分不一致** | 实测：main 与候选在 `changed` 上**都是 52/52**，**没有"漏掉事件"**；MAIN 把 **28/28** 跨盘标成幅度（无翻转概念），CAND 标对 **18/28**、漏判 **10**、并**假判 2** |

**裁决：主 Agent 的复算更精确。** 关键区分：
- "**漏掉事件**"（`changed=False`）→ **两版都是 0 例**。main 与候选在"是否产生 LINE_CHANGE"上完全一致。
- "**分类错误**"→ main 28/28 跨盘全部分类为幅度；候选 12/52 错误（10 漏判 + 2 假判），**全部源于 `-0`**。
- 候选相对 main 的**净收益**：跨盘识别 0 → 18（64%）；**净损失**：2 条假跨盘。

D 的"漏掉 10 条"应表述为"**未识别为跨盘**"，而非"漏掉事件"。此修正已写入 `04_REAL_DATA_EVIDENCE.md` §3。

---

## 5. Agent D 提出的、主 Agent 前一轮遗漏的新缺陷（全部已复现或标注）

| ID | 内容 | 复现状态 |
|---|---|---|
| **CE2/CE3** | `parse_line_quarters` 自身缺陷：`round()` 银行家舍入 → `"0.125"→"0:0"`、`"0.625"→"2:2"`；`"--0.5"→"2:2"`（双符号未拒绝）；`"inf"`/`"1e400"` 抛 `OverflowError`（`except` 只捕获 TypeError/ValueError） | **已由主 Agent 实测复现**（`verify_boundary_output.txt` D 节） |
| **CE4** | `mid` 是 floor 不是中点：`"-0.5/-0.25"→("-2:1", -1)` | 已实测 |
| **CE5** | 规范与事件链路**口径相反**：`parse_line_quarters("-0/0.5")` = `-2:0`/`-1`（负） vs `events/line.py` = `+0.25`（正） | 已实测 |
| **ND1** | `-0` 缺陷的真实影响面：52 条迁移中候选错 12 条，且**同一市场变动在两侧被不同标注** | 已复算（数字已修正） |
| **ND3** | `parse_line_quarters` 的 `OverflowError` 在两个调用方均未防护 → 可崩溃 | 已复现 |
| **CE13** | `af2db46` 的 P1-4 修复 `line = float(raw_line)` 会使 **46.2% 真实行 `line=None`**，而 `engine_v3.py:42` 的 `abs((x["line"] or 0)-...)` 把 NULL 当 0 配对 → **不能直接 cherry-pick** | Agent D 实测；主 Agent 采信并写入 `05_FIX_PLAN.md` 阶段 4 前置条件（**未独立复算 46.2%**） |
| **CE12** | 候选改变 `changed` 集合 → 回放 `replay_hash` 变化 → 回放行重插 | 采信，写入 §2 |

---

## 6. 未决问题（UNRESOLVED，需领域/规格裁定）

1. **U1 — 跨盘是否需要独立事件类型？** 现有枚举 `DEEPER/SHALLOWER/SAME/UNKNOWN` 无"跨盘"概念。两种方案见 `05_FIX_PLAN.md` 阶段 3（3a 独立布尔字段 / 3b 新枚举）。**无任何仓库证据可判定**（规格文件缺失）。
2. **U2 — "同一盘口"与"有效盘口"的正确定义**：以 `quarters`（腿对）判同，还是以 `mid`（中点）判同？两者在 `"0.125"` 等非 0.25 倍数上不一致（`0:0` vs mid 0）。真实数据只有 0.25 倍数，**实操上等价**，但定义层未裁定。
3. **U3 — `steps` 的单位**：统一为 `|Δmid|`（四分之一球）后，幅度变化与跨盘变化是否可共用一个标量？跨盘的"位移"与幅度的"变动"物理含义不同。
4. **U4 — `line`（数值）字段是否应随 `line_raw` 同源**：上游改了，但会让大量行变 NULL（CE13），需要数据库语义决策。
5. **U5 — `canonical_match_id` 在生产链路上是否真的为 NULL**（HP-3）：代码上 `sources/bb.py:59` 恒为 None，但 `mapping/service.auto_map` 是否在别处回填，本次**未查证调用方** → **UNKNOWN**。
6. **U6 — 规格文件 BBN-PRD-ARCH-SPEC V1.0 的内容**：§5.2 / §9-11 / §19 / 规则 7.1 / 9.2 / 39 均被引用但文件不在仓库。

---

## 7. 冲突未抹平说明

- 分歧二（契约冲突严重度）保留双方主张，裁决为"降级为低，但指出被低估的真风险"——两方证据均保留在 §3。
- 分歧四（数字 10 vs 0）保留 D 的原始表述与主 Agent 的复算结果，明确标注 D 的"漏掉"应理解为"未识别为跨盘"。
- U1–U6 **保持 UNRESOLVED**，本报告不代替领域决策。
