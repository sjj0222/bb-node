# 07_RUN_LOG.md

## 环境与边界

| 项 | 值 |
|---|---|
| 仓库根 | `/data/data/com.androidharness.app/files/github-projects/bb-node-a6ff0096` |
| 分支 / HEAD | `main` / `74cff43929f997f9f72fdbae8649b39221b8b4b8`（15 commits，调查前后未变） |
| 隔离副本 | `<repo>/devcopy/`（自带独立 `.git`，同 HEAD；`pushurl=blocked://no-push-from-dev-copy` + `pre-push` 钩子 exit 1） |
| 副本既有改动 | `M events/line.py`、`?? tests/__init__.py`、`?? tests/test_line.py`（BB-D1 候选，本轮**未改动**） |
| Python | 3.14.8；`PYTHONDONTWRITEBYTECODE=1` 用于**全部** Python 调用 |
| 交付目录 | `<repo>/devcopy/.harness_tmp/`（**在 devcopy 之内，正式项目之外**） |
| 外部目录尝试 | `/tmp`（可读可执行，`cwd` 用）、`/var/tmp`（被 harness 拦截）、`/data/local/tmp`（被 harness 拦截）、`$HOME`（只读可用）→ 交付物最终落在 `devcopy/.harness_tmp/` |

## 工具限制记录
- `find`/`ls`/`cat` 等对**工作区外**路径被 harness 拦截（`..`、`/var/tmp`、`/data/local/tmp`、`/data/data/.../github-projects/` 父目录）→ 无法访问仓库外原始 CSV（`~/odds_data/snapshots/*.csv`），**已按"缺失证据"记录，未伪造**
- `git` 只读命令均加 `--no-optional-locks`，避免刷新索引

## 实际执行的命令（按阶段）

### Phase 0 启动检查
```
pwd; git rev-parse --show-toplevel; git rev-parse --abbrev-ref HEAD; git rev-parse HEAD
git status --porcelain -uall; git log --oneline -3
ls -la devcopy/; git -C devcopy rev-parse --show-toplevel; git -C devcopy status --porcelain -uall
git -C devcopy diff --name-status HEAD
```
→ 退出码 0。确认：正式项目 `?? devcopy/`；devcopy 为独立仓库，BB-D1 改动 = 3 个文件。

### Phase A 规范权威性
```
git diff --name-status main origin/phase1
git log --oneline main..origin/phase1 ; git log --oneline origin/phase1..main
git show origin/phase1:mapping/market.py | grep -n -A 80 parse_line_quarters
git show origin/phase1:events/line.py
git diff --stat main origin/phase1 -- events/line.py        # 空
git ls-tree -r --name-only origin/phase1 | grep -iE "spec|test|line|doc|accept|market"
git show origin/phase1:tests/test_line.py
git show origin/phase1:tests/test_phase6.py | grep -n "quarters|parse_line|0/0.5|line"
git show --stat af2db46
git show origin/phase1:sources/bb.py | grep -n "mk_line|li\b|line"
git show origin/phase1:market/registry.py
git show origin/phase1:market/selector.py
git show origin/phase1:mapping/unified_db.py | grep -n "market_definition_id|line_quarters"
```
→ 全部退出码 0。

### Phase B 边界值（只读脚本，cwd=/tmp）
```
PYTHONDONTWRITEBYTECODE=1 python3 devcopy/.harness_tmp/verify_boundary.py   → exit 0
PYTHONDONTWRITEBYTECODE=1 python3 devcopy/.harness_tmp/verify_claims.py    → exit 0
PYTHONDONTWRITEBYTECODE=1 python3 devcopy/.harness_tmp/verify_matrix.py    → exit 0
```
输出落盘：`verify_boundary_output.txt` / `verify_claims_output.txt` / `verify_matrix_output.txt`。
早期两次交互式边界测试亦已留档：`boundary_test_main.txt`、`boundary_test_devcopy.txt`、`comparison_test.txt`。

### Phase C/D 数据流与契约
```
cat sources/bb.py mapping/match.py mapping/service.py mapping/market_service.py \
    mapping/unified_service.py mapping/db.py mapping/market_db.py mapping/unified_db.py \
    events/engine_v3.py replay/event_v1.py replay/event_v2.py        (→ 02_EVENT_DATAFLOW.md 附录)
grep -rn "line_direction\|line_change_type" --include=*.py devcopy
grep -rn "DEEPER|SHALLOWER|QUARTER_STEP|..." --include=*.py devcopy
```
→ 退出码 0。

### Phase F 真实数据
```
wc -l ladder.txt ladder_v7.txt
tr ',' '\n' < ladder.txt | sed 's/^[^:]*://' | sed 's/:[0-9.]*$//' | sort | uniq -c | sort -rn
grep -cE '[: ,]0/0\.5' ladder.txt ladder_v7.txt      → 0 / 0
grep -c -- "-0.5/0" ladder.txt ladder_v7.txt          → 0 / 0
grep -c -- "+0.5/0" ladder.txt ladder_v7.txt          → 0 / 0
grep -c -- "-0/0.5" ladder.txt ladder_v7.txt          → 342 / 12
grep -c -- "+0/0.5" ladder.txt ladder_v7.txt          → 342 / 12
grep -nE "MARKET_CHANGE|^ [+-] " ladder_v7.txt
```
→ 退出码 0。

### Phase H 独立 Agent（4 个，只读子 Agent）
| Agent | 任务 | 产出 |
|---|---|---|
| A | 规范权威性 + Git 历史 | 逐函数表、5 分支 grep、契约原文 |
| B | 源→事件数据流 | 10 条高风险路径 + CLEAN 清单 |
| C | 测试质量/边界 | `agentC_test_audit.txt` |
| D | 反方审计 | `agentD_adversarial.txt`（13 反例 / 3 最弱结论 / 4 新缺陷） |

主 Agent 对 D 的关键数字做**独立复算**（`verify_matrix.py`），其中 1 项（"漏掉 10 条"）**修正为**"未识别为跨盘，事件本身未漏"，已在 `06_AGENT_DISAGREEMENTS.md` §4 记录。

## 未执行的命令及原因

| 未执行 | 原因 |
|---|---|
| `pytest` / `python -m unittest`（任何分支） | `main` 无 tests/；上游测试依赖会 import 写库模块（`core/log.py:69` import 期建库），无隔离副本时不满足"确认执行安全性"的前置条件 |
| `git commit/push/checkout/reset/clean/stash` | 任务禁止；副本已配置推送阻断 |
| 读取 `~/odds_data/snapshots/*.csv` | harness 拦截工作区外路径；**已记录为缺失证据** |
| 读取规格文件 `BBN-PRD-ARCH-SPEC V1.0` | **仓库任何分支均不存在**（5 分支 `ls-tree` 无匹配）→ UNKNOWN |
| 修改任何项目源文件 | 任务禁止（只读调查） |

## 安全检查（最终态）

| 检查 | 方法 | 结果 |
|---|---|---|
| 正式项目受跟踪文件未变 | `git ls-files -z \| xargs -0 sha256sum \| diff -u <任务前清单> -` | 49/49 一致（diff 空） |
| 正式项目无未跟踪/忽略产物 | `git status --porcelain --ignored -uall` | 仅 `?? devcopy/` |
| 正式项目无 `__pycache__`/`.pyc`/`.db`/`.log` | `find` 排除 devcopy | 无 |
| 副本内无 `__pycache__`/`.pyc`/`.db` | `find devcopy` | 无（脚本均在 /tmp 下运行且 `PYTHONDONTWRITEBYTECODE=1`） |
| Git 状态未改 | 两仓库 `rev-list --count` = 15；reflog 无新条目 | 未改 |
| 唯一写入位置 | `devcopy/.harness_tmp/`（devcopy 为独立副本，正式项目之外） | 已记录 |

> 声明：可验证范围内**未发现**对正式项目或 `devcopy/` 源文件的任何写入。由于文件系统时间戳会被 harness 的只读工具自身更新（例如 `.git/index` 的 stat 缓存刷新），**不能声称"绝对零副作用"**，只能声明上述已逐项核验的结论。
