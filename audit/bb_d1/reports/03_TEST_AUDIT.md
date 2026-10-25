# 03_TEST_AUDIT.md

> 本轮**未运行**测试套件（约束：避免任何副作用）。测试结论均来自**读代码**与**上游分支内容比对**。
> 分类标记：STRONG / WEAK / TAUTOLOGICAL / WRONG。来源：Agent C 独立审查 + 主 Agent 复核。

---

## 1. 测试资产盘点

| 分支 | 测试文件数 | 说明 |
|---|---|---|
| `main` | **0** | 无 `tests/` 目录，无 CI 配置 |
| `origin/phase1` | 33 | 含 `tests/test_line.py`、`tests/test_phase6.py`、`tests/test_audit_p0..p3.py` 等 |
| `origin/v0.2` | 18 | `tests/test_line.py` 与 phase1 版**逐字节相同**（8 例） |
| `origin/phone-sync` / `origin/ai-memory-v0.1` | 0 | — |
| `devcopy/`（未提交） | 1 + `__init__.py` | BB-D1 候选新增 23 例（418 行），**未纳入任何 git 提交** |

**没有任何分支的测试引用 `ladder.txt` / `ladder_v7.txt`** → **不存在真实数据快照回归测试**（CODE/GIT）。

---

## 2. `devcopy/tests/test_line.py` 逐例评价

| 行 | 测试方法 | 分类 | 依据 |
|---|---|---|---|
| 65 | `test_ac1_sign_flip_is_detected` | WEAK | 只断言 `changed is True`；被 78 覆盖 |
| 78 | `test_ac1b_sign_flip_is_classified_as_cross_sign_flip` | STRONG | 硬编码 `CROSS`/`SIGN_FLIP` |
| 90 | `test_ac1b_..._steps_equal_quarter_goal_units_of_total_movement` | STRONG* | 硬编码 4.0/2.0/7.0/10.0；*期望语义本身未经规格确认 |
| 109 | `test_ac1b_..._steps_concrete_values` | STRONG | 硬编码 |
| 117 | `test_ac2_equivalent_spellings_are_unchanged` | STRONG | 4 组硬编码 |
| 131 | `test_ac2b_identical_spellings_are_unchanged` | WEAK | 冗余 |
| 146 | `test_ac3_regression_magnitude_cases_keep_pre_fix_classification` | STRONG | 11 组硬编码，值与 main 实测一致 |
| 168 | `test_ac3_zero_is_neutral_and_is_not_a_sign_flip` | STRONG | — |
| 182 | `test_ac3b_legacy_multi_step_classification_is_preserved` | STRONG* | oracle = 原实现输出（自证），但值可由 main 独立复核 |
| 195 | `test_ac4_unparsable_input_returns_unknown` | STRONG | 6 组 |
| 213 | `test_ac5_norm_keeps_raw_legs_and_depth_unchanged` | STRONG | 硬编码 |
| 239 | `test_ac5_norm_exposes_signed_value_additively` | STRONG | 硬编码（但口径与规范不一致，见 §4） |
| 248 | `test_ac5_norm_value_keeps_full_float_precision` | WEAK | 无下界 |
| 257 | `test_ac5_parse_line_is_untouched` | **TAUTOLOGICAL** | `GOLDEN_PARSE_LINE`（L35-49）是 `devcopy/events/line.py:1-15` 的**逐字副本**；且把 `"-0/0.5"` 的 bug 一并冻结为"期望" |
| 276 | `test_ac5_import_pulls_no_project_modules_and_no_io_modules` | WEAK | L283-285 的集合恒等式恒真；依赖 import 顺序 |
| 294 | `test_ac5_import_creates_no_file_in_a_fresh_directory` | WEAK | 子进程 cwd=临时目录，**不是模块目录**；且自行设 `PYTHONDONTWRITEBYTECODE=1` |
| 329/342/351 | boundary whitespace / zero / asymmetric depths | STRONG | — |
| 359 | `test_boundary_depth_equality_is_exact_like_the_original` | **TAUTOLOGICAL** | 断言的 `3.999999886872274e-09` 就是实现自身的 IEEE754 结果 |
| 369/392 | sub-EPS / tiny crossing | STRONG | — |
| 411 | `test_module_under_test_is_this_devcopy` | STRONG | — |

**结论**：23 例中 **2 例同义反复**、**5 例偏弱**，**16 例为有效断言**。

---

## 3. 上游契约与候选实现的兼容性

- 上游 `origin/phase1:tests/test_line.py` 全部 8 条断言在候选实现下**仍然成立**（Agent A 实测）→ 候选**未破坏**上游既有测试
- 但上游测试**锁定的是旧枚举集合**，未断言"枚举集合不变"，因此上游测试**无法**发现候选新增 `CROSS`/`SIGN_FLIP` 这一契约变更

---

## 4. 测试盲区（按严重性）

| ID | 严重性 | 盲区 | 证据 |
|---|---|---|---|
| D1 | **CRITICAL** | **负零分盘被读成正向** → 候选产生**假** `SIGN_FLIP`；若把实现改成"正确"的 `value=sign*mean(|legs|)`，23 例**仍全绿**；而 L257 反而**禁止**该修正 | 实测 `verify_boundary_output.txt`：`'-0/0.5'` 候选 value=+0.25，规范 mid=-1 → NO；`compare_line("-0/0.5","-0.5/0")` → `CROSS/SIGN_FLIP` |
| D2 | **CRITICAL** | **混合符号腿**：`"-1/+1"` vs `"+1/-1"` → 判 `SAME`；vs `"-1/-1"` → `changed=True` 且 `steps=0.0`（恰是 L376 自己禁止的形状） | 实测 `verify_boundary_output.txt`：`'-1/+1'` 候选 value=0.0 |
| D3 | HIGH | `steps=0.0` 的矛盾输出在 EPS 边界仍可出现 | Agent C 实测 |
| D4 | HIGH | **EPS 常量未钉死**：`EPS` 取 1e-6 / 5e-6 / 1e-10 等仍能通过 23 例 | Agent C 实测（变异存活） |
| D5 | HIGH | `round(...,4)` 使小于 0.0025 的步数被抹平；L400 把该产物固化为期望 | Agent C |
| D6 | MED | `steps` 在两个分支量纲不同（深度空间 vs 值空间） | CODE（`devcopy/events/line.py:80` vs `:101`） |
| D7 | MED | **返回键集合未断言**：给结果字典加一个 `extra` 键、或给 `norm()` 加 `polarity` 键，23 例**全部存活** | Agent C 实测 |
| D8 | MED | **`steps` 类型未断言**（int 0 vs float 0.0 无人把关） | Agent C |
| D9 | MED | **消费方零覆盖**：`events/engine_v3.py` / `replay/event_v1.py` / `replay/event_v2.py` 的配对逻辑（`min(cand,key=abs(line 差))`）**没有任何测试** | GIT：全分支无对应测试 |
| D10 | MED | 无跨 `market_id` 错配对测试、无 `line`/`line_raw` 不同源测试 | 同上 |
| D11 | LOW | L280 的纯度断言**依赖 import 顺序**（若先 import 了 `events/engine_v3.py`，会拉入 `core.log` 而失败） | Agent C 实测 |
| D12 | LOW | 无真实数据回归 | GIT |

---

## 5. 对"测试通过 ≠ 业务正确"的具体证明

候选 23 例全绿的前提下，以下事实同时成立（全部实测）：
1. `"-0/0.5"` 被判为 **+0.25**，而项目自有规范判为 **-0.25**
2. `"-0/0.5"` 与 `"-0.5/0"`（规范等价）被判为 `CROSS/SIGN_FLIP`（假阳性）
3. 真实 52 条迁移中，候选 **10 条漏判跨盘、2 条假判跨盘（23% 错误率）**
4. `"-1/+1"` 产生 `changed=True` 且 `steps=0.0`
5. 规范函数 `parse_line_quarters` 自身对 `"--0.5"` 返回 `"2:2"`、`"0.125"` 返回 `"0:0"`、`"inf"` 抛 `OverflowError` —— **即"权威规范"也不是无条件正确**

→ **单元测试通过完全不能证明业务语义正确**（CODE + 实测）。

---

## 6. 最小测试补强建议（供修复阶段执行）

1. 引入**独立 oracle**：以 `parse_line_quarters` 的 quarters/mid 作为"同一盘口"与"跨盘"的判据，断言候选实现与之**逐条一致**（52 条真实迁移全量回归）
2. 增加负零族用例：`"-0/0.5"`, `" -0/0.5 "`, `"-0 / 0.5"`, `"-0"`, `"+0"`
3. 增加混合符号与畸形输入：`"-1/+1"`, `"--0.5"`, `"+-0.5"`, `"inf"`, `"1e400"`, `"0.125"`
4. 断言**返回键集合**与 `steps` 类型（`changed is True` 时 `steps` 必须为正数）
5. 把 EPS 常量钉死为具名常量并断言边界行为
6. 为 `events/engine_v3.py` 配对写**假数据**测试：同 market_id 不同档位、`line` 与 `line_raw` 不一致、`canonical_match_id=None`
