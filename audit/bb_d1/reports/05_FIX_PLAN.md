# 05_FIX_PLAN.md

> 本计划**未实施**。所有文件均未修改。
> 前提：本计划假定"上游 `parse_line_quarters` 的 quarters/mid 口径"是项目期望的业务语义 —— 该前提**尚未被规格文件证实**（规格文件不在仓库），因此每一阶段都给出了"若前提不成立"的分支。

---

## 0. 为什么不能直接合并当前 BB-D1 候选

实测（`devcopy/.harness_tmp/verify_matrix_output.txt`）：

| 指标 | 数值 | 含义 |
|---|---|---|
| 真实 52 条迁移中，候选分类错误 | **12（23%）** | 10 漏判跨盘 + 2 假判跨盘 |
| 错误根因 | **100% 集中在 `parse_line` 的 `-0` 符号丢失** | 一处根因 |
| 候选与规范口径不一致的边界输入 | `"-0/0.5"`、`" -0/0.5 "`、`"-0/0.5 "`、`"-0 / 0.5"`、`"-1/+1"` | 5 类 |
| `changed=True` 但 `steps=0.0` | 可复现（`"-1/+1"` vs `"-1/-1"`） | 自相矛盾输出 |
| `steps` 量纲 | 幅度分支=深度差，CROSS 分支=值差 | 同名不同义 |
| `CROSS`/`SIGN_FLIP` 在全历史 | 0 命中 | 未入规范 |

**核心问题**：BB-D1 在**错误的解析层**（`events/line.py::parse_line`，本身有 `-0` bug）之上另建了一套 `value` 口径，结果与项目自有的 `parse_line_quarters` 不一致，且在真实数据最常见的 `-0/0.5` 上直接算错。

---

## 1. 五个方案评估

| 维度 | A：只修比较逻辑 | B：先修负零，保留契约 | **C：统一四分之一球编码** | D：先修源字段与配对 | E：分阶段拆分 |
|---|---|---|---|---|---|
| 业务语义正确性 | 低（口径未规范化，`-0` 未解） | 中（修好 `-0` 后语义自洽，但与项目规范仍两套口径） | **高**（与项目自有 `parse_line_quarters` 对齐） | 高（解决配对，不解决分类） | 高（可增量验证） |
| 与既有契约兼容 | 差（新增词表） | **好**（枚举不变） | 中（枚举需增补，但可复用 DEEPER/SHALLOWER） | 好 | 中 |
| 对历史数据影响 | 改变 `changed` 集合 → 事件条数与 replay hash 变化 | 同左 | 同左，但分类更准 | 改变行配对 → 事件条数变化 | 分阶段可控 |
| 可能引入的新缺陷 | 假/漏翻转（实测 23%） | 混合符号腿仍矛盾 | `parse_line_quarters` 自身缺陷（`--0.5`→`"2:2"`、`0.125`→`"0:0"`、`inf`→OverflowError） | `line` 变 NULL 风险（Agent D CE13：af2db46 使 46.2% 真实行 `line=None`） | 阶段间接口漂移 |
| 需要回归测试 | 现有 23 例 + 52 条真实迁移 | 现有 23 例 + 负零族 | **必须**用 `parse_line_quarters` 做独立 oracle 的全量回归 | 需要假数据配对测试 | 每阶段各一套 |
| 修改文件范围 | 1 | 1–2 | 2–3（新增规范化层） | 4–6（sources + 引擎 + 回放） | 逐步扩大 |
| 回滚难度 | 低（单文件） | 低 | 低 | 中（涉及 schema 语义） | 低 |
| 当前证据是否足以实施 | **否** | **是** | **部分**（口径可信但需补规格；plq 需加固） | **否**（缺运行数据） | 阶段 1–2 是 |

**推荐：C 为主线，E 为执行方式；D 单独排期（需运行数据与数据库决策），A/B 放弃。**

---

## 2. 分阶段最小修复方案

### 阶段 1（P0，阻塞其余全部）— 负零与畸形输入的正确处理
**目标**：让"解析"层对负零、畸形、超范围输入行为确定。
**改动**：`events/line.py::parse_line`（或新增统一规范化模块）
- 负零：不要用 `x < 0` 判定符号。改为**先抽前缀符号，再作用于全部腿**（与 `parse_line_quarters` 同法），或用 `math.copysign` / 原始字符串前缀判定
- 畸形：`"--0.5"`、`"+-0.5"`、`"1/2/3"` 必须拒绝（当前 main 已拒绝，需保持）
- 非有限值：`"inf"`、`"1e400"` 必须拒绝（当前 main **静默接受** → `depth=inf`）
- **验收**：`parse_line("-0/0.5")` 的两腿符号与 `parse_line_quarters("-0/0.5")` 一致（mid=-1）；`parse_line("inf") is None`
- **回归**：负零族 5 用例 + 畸形族 4 用例 + 原有 11 组幅度用例全部保持
- **回滚**：单文件还原

### 阶段 2（P0）— 引入唯一规范化层并用 quarters 判等
**目标**：消除"两套口径"。
**改动**：新增 `events/line_spec.py`（或把 `parse_line_quarters` 移植进 `events/line.py`），导出 `normalize_line(raw) -> (quarters, mid)`；`compare_line` 内部改为：
- `quarters` 相同 ⇒ `changed=False, SAME/SAME, steps=0`（**等深异号翻转与等价写法同时解决**）
- `mid` 异号且均非 0 ⇒ 变化，且方向按**带符号 mid**（`CROSS` 是否新增见阶段 3）
- 否则 ⇒ 现有 `DEEPER/SHALLOWER` + `QUARTER/HALF/MULTI_STEP`，`steps` **统一为 `|Δmid|` 的四分之一球数**（消除双量纲）
**前置**：先加固 `parse_line_quarters` 的三个已知缺陷：
- `round()` 银行家舍入 → 改用 `int(Decimal(x)*4)` 或 `math.floor(x*4+0.5)`
- `"--0.5"` 等双符号输入必须拒绝
- `inf`/`1e400` 必须捕获 `OverflowError`
**验收**：52 条真实迁移上，`quarters` 判定与 `parse_line_quarters` **逐条一致**；`steps` 在所有分支同量纲
**回归**：以 `parse_line_quarters` 为**独立 oracle** 的全量测试（当前测试全部以实现自身为 oracle，必须替换）

### 阶段 3（P1，需业务确认）— 事件分类词表
**两个选项**：
- **3a（低风险，推荐先做）**：**不新增枚举**。跨盘时仍输出 `DEEPER`/`SHALLOWER`（按 `|Δmid|`），把"是否跨盘"作为**独立布尔字段**（如 `crossed: bool`）返回并落库
- **3b**：引入 `CROSS`/`SIGN_FLIP`，同时更新 `origin/phase1:tests/test_line.py` 的契约文档与所有落库字段说明
**注意**：`changed` 的取值集合若发生变化，`LINE_CHANGE` **事件条数**会变 → `replay/event_v1.py` 的 `event_count`/`replay_hash` 变化 → 回放行需重新基线（Agent D CE12）
**前置**：领域负责人对"跨盘是否需要独立事件类型"的裁定
**验收**：新字段在 `events_v3` 与 `replay_events_v2` 的 schema 与写入语句中一致

### 阶段 4（P1，独立排期）— 源字段一致性与事件配对
**改动**（**不要直接 cherry-pick `af2db46`**，Agent D CE13：其 `line = float(raw_line)` 会使 46.2% 真实行 `line=None`，进而使 `engine_v3.py:42` 的 `abs((x["line"] or 0)-...)` 把 NULL 当 0 配对）：
- `sources/bb.py`：`line` 与 `line_raw` 同源（选项级 `op.li`），且**保留盘口级 `mk.li` 到独立字段**（不要丢信息）
- `events/engine_v3.py`：配对键加入稳定的盘口观察系列标识（`(match, mty, pe, option)`，而非仅 `side/option`），并显式排除跨 `market_id` 的行
- `events_v3` schema 增加 `source_market_id` 以便下游察觉错配
**前置**：需要运行数据与数据库变更决策（**当前证据不足，BLOCKED**）

### 阶段 5（P2）— 修复下游断链与 DB 路径分裂
- `features/engine_v1.py` / `engine_v2.py` 补 `CREATE TABLE IF NOT EXISTS features_v1/features_v2`（HP-6）
- `events/group_v3.py` 加 `if __name__=="__main__"` 守卫（HP-5）
- 统一 DB 路径为单一真源（HP-8）
- 统一事件引擎与回放引擎的时间窗（HP-4）

---

## 3. 验收标准（阶段 1–2 的合并验收）

1. `parse_line("-0/0.5")` 与 `parse_line_quarters("-0/0.5")` 的符号/中点一致
2. 52 条真实迁移：规范化后 `quarters` 判定与 `parse_line_quarters` **逐条相同**；跨盘识别率 100%（当前 main 0%、候选 64%）
3. 候选的真值表用例（`"-0/0.5"` vs `"-0.5/0"`）判为 **SAME**
4. 非法输入族（`""`, `None`, `"abc"`, `"1/2/3"`, `"--0.5"`, `"inf"`, `"1e400"`）全部 `None` / `UNKNOWN`
5. 不存在 `changed=True` 且 `steps==0` 的输出
6. `steps` 在所有分支单位一致
7. 现有 `origin/phase1:tests/test_line.py` 8 条断言**仍然通过**（不改断言）
8. 新增测试以 `parse_line_quarters`（或一份独立手写真值表）为 oracle，**禁止**以实现自身为 oracle
9. 正式项目与 `devcopy/` 之外的路径零写入；`git status` 无新增产物

---

## 4. 回滚方式

- 每阶段一个独立 commit 落在 `devcopy/`（**不得推送到 origin**；`devcopy` 已配置 `pushurl=blocked://no-push-from-dev-copy` + `pre-push` 钩子拒绝推送）
- 阶段 1 可用 `git checkout -- events/line.py` 单文件回滚
- 阶段 2 若引入新模块，回滚 = 删除新模块 + 还原 `events/line.py`
- 阶段 4 涉及 schema，需单独备份 `unified_snapshots` / `events_v3` 后再改

---

## 5. 停止条件（触发即停并上报，不得自行决定业务定义）

1. 领域负责人未裁定"跨盘是否需要独立事件类型" → 阶段 3 停止
2. 规格文件（BBN-PRD-ARCH-SPEC V1.0 / §5.2）不可得 → 阶段 2 的"以 quarters 为准"只能作为**假设**实施，必须在代码与测试中显式标注该假设
3. 原始 CSV 不可得 → 无法证明"等深异号翻转"真实存在，阶段 2 完成后仍**不得**宣称 BB-D1 的原始目标已验证
4. 任何阶段需要修改 `sources/bb.py` 的 `line` 语义 → 触发 HP-4/HP-7 连锁，需先取得数据库与运行数据决策
