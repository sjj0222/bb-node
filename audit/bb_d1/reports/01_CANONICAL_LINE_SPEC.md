# 01_CANONICAL_LINE_SPEC.md

> 证据类别标记：**CODE**=当前代码直接证明 · **TEST**=现有测试直接证明 · **DATA**=真实原始数据直接证明 · **GIT**=Git 历史直接证明 · **INFERENCE**=由上述推导 · **UNKNOWN**=材料不足
> 所有"实测"数字来自 `devcopy/.harness_tmp/verify_boundary.py` / `verify_matrix.py` / `verify_claims.py`
> （只读脚本，`PYTHONDONTWRITEBYTECODE=1`，cwd=/tmp，未导入任何写库模块，未在仓库内产生 `__pycache__`）

---

## 1. 逐函数对照表

| 文件/函数 | 输入格式 | 解析算法 | 符号规则 | 输出单位 | 调用者 | 既有测试 | 风险 |
|---|---|---|---|---|---|---|---|
| `events/line.py:1-15` `parse_line` (main) | 单值 / `a/b` | `/` 分两腿；`float()` | **二腿无符号时继承首腿**（`x<0`） | 原始腿值（float） | `events/line.py:19 norm`、`:31-32 compare_line`；经 `from events.line import compare_line` 被 `events/engine_v3.py:2`、`replay/event_v1.py:2`、`replay/event_v2.py:2` 引用 | `origin/phase1:tests/test_line.py`（8 例） | **HIGH**：`x<0` 对 `-0.0` 为 False → `"-0/0.5"` 符号丢失；`float("inf")` 被接受为合法盘口；无上限校验 |
| `events/line.py:18-27` `norm` (main) | 同上 | 求 `depth=Σ|x|/n` | **无符号信息**（仅绝对值） | 绝对深度（球） | `compare_line` | 同上 | **HIGH**：符号信息在 norm 层即被丢弃，是 BB-D1 缺陷的根因 |
| `events/line.py:30-72` `compare_line` (main) | 两个盘口串 | 仅比 `depth` | 无 | `steps`=四分之一球数 | 3 个事件/回放引擎 | 同上 | **HIGH**：等深异号翻转被判 `SAME`；`change_type` 只有 3 档 + SAME/UNKNOWN |
| `devcopy/events/line.py` (BB-D1 候选) | 同上 | 比 `depth` **且** 比新增 `value`=Σlegs/n | 新增 `value`（有符号均值） | `steps` 在 CROSS 分支=四分之一球、在幅度分支=四分之一球（**两种量纲**） | 同上 | `devcopy/tests/test_line.py`（23 例，未提交） | **HIGH**：新增 `value` 与项目自有 `parse_line_quarters` 口径不一致（见 §4）；`CROSS`/`SIGN_FLIP` 历史上不存在 |
| `mapping/market.py:29-47` `parse_line` (main) | 单值 / `a/b` | 两腿算术平均 | **完全丢弃符号** | 绝对值（球） | `mapping/market.py:69 normalize` → `market_mappings.line` | `origin/phase1:tests/test_mapping_market.py` | **MEDIUM**：`"-0/0.5"` 与 `"+0/0.5"` 都得 0.25 → 同一 market 两选项无法区分 |
| `events/group_v3.py:9-16` `depth` | 单值 / `a/b` | `round((|a|+|b|)/2,4)` | 丢弃符号 | 绝对深度（球） | `group_v3.py:21` 分组键 | 无 | **MEDIUM**：与 `norm().depth` 口径一致但自带舍入；模块级有写库副作用 |
| `mainline_v4.py:3-10` `dep` | 单值 / `a/b` | 绝对值平均 +「二腿更小则取首腿」 | 丢弃符号 | 绝对深度 | `mainline_v4.py:19-20` | 无 | **LOW**：探索脚本，规则与规范不同 |
| `mainline_v5.py:6-13` `depth` | 同上 | 绝对值平均 | 丢弃符号 | 绝对深度 | `mainline_v5.py:36` | 无 | **LOW**：同上 |
| `mainline_v6.py:6-13` `depth` | 同上 | 同 v5 | 丢弃符号 | 绝对深度 | `mainline_v6.py:34` | 无 | **LOW**：同上 |
| **`origin/phase1:mapping/market.py:69-107` `parse_line_quarters`** | 单值 / `a/b` | 四分之一球整数化 `round(x*4)`，符号作用于**全部腿**，排序，取 `mid=(q0+q1)//2` | **符号整行生效**（不依赖 `x<0`） | **四分之一球整数**（`quarters` 串 + `mid`） | `mapping/market.py:160 normalize`（写 `line_quarters`）、`origin/phase1:quality/validator.py:96` | `origin/phase1:tests/test_phase6.py:23-48`（含 R1 回归） | **MEDIUM**：非规范输入不报错（`"--0.5"`→`"2:2"`）；`round()` 银行家舍入（`"0.125"`→`"0:0"`）；`inf` 抛 `OverflowError` 未被捕获；`mid` 是 floor 非中点；**main 与 origin/phase1 的事件链路都不调用它** |

---

## 2. 权威性判定

**结论：`parse_line_quarters` 是"市场映射层"的规范化实现，但**不能**认定为"盘口变化分类"的权威规范。（CODE+GIT+INFERENCE）**

| 判据 | 证据 | 指向 |
|---|---|---|
| 是否在仓库中存在规格文件 | `git ls-tree -r --name-only` 扫描 main / origin/phase1 / origin/v0.2 / origin/phone-sync / origin/ai-memory-v0.1：**无任何规格文件**；`git log --all -S'BBN-PRD-ARCH-SPEC'` 仅命中 `origin/phase1:docs/RELEASE_NOTES.md:5` 的一句引用，文件本身不在任何 tree 中 | **UNKNOWN**：§5.2 的原文不可核实 |
| 是否有测试固化 | `origin/phase1:tests/test_phase6.py:23-28` 断言 `parse_line_quarters("-0/0.5") == ("-2:0", -1)`，注释「R1 修复: '-0/0.5' 不得反转成 +0.25」 | **TEST**：强证据，但只覆盖映射层 |
| 事件链路是否使用 | `git show origin/phase1:events/engine_v3.py:34,53` → 仍然 `from events.line import compare_line`；`git diff main origin/phase1 -- events/line.py` **为空** | **CODE/GIT**：事件分类链路**从未**采用该规范 |
| main 是否有任何调用 | `git show main:mapping/market.py \| grep -c parse_line_quarters` → **0** | **CODE**：main 完全未集成 |
| 最早出现的函数 | `git log --all --diff-filter=A --format='%h %ad %s' --date=short -- events/line.py` → `f993b8c 2026-09-05 init: bb odds collector core`；`parse_line_quarters` 首次出现于 `59d670e 2026-10-21 Phase 6: 盘口字段规范与主盘口选择器 (规格 §5, R1 修复)` | **GIT**：`parse_line_quarters` 比 `events/line.py` **晚约 6 周** |

> ⚠️ 不得仅因 `parse_line_quarters` "更完整"就认定它是正式规范（任务明确禁止此推断）。目前可判定的最强表述是：
> **它是上游在映射层自行实现、带有 R1 回归测试、且与 `events/line.py` 的既有契约不一致的第三套口径。**

---

## 3. 边界值完整矩阵（实测）

脚本：`devcopy/.harness_tmp/verify_boundary.py` → 输出 `verify_boundary_output.txt`

| 输入 | main `parse_line` legs | main depth | 候选 `value` | 规范 quarters | 规范 mid | 候选 == 规范 |
|---|---|---|---|---|---|---|
| `'-0/0.5'` | `[-0.0, 0.5]` | 0.25 | **+0.25** | `-2:0` | **-1** | **NO** |
| `'+0/0.5'` | `[0.0, 0.5]` | 0.25 | +0.25 | `0:2` | +1 | YES |
| `'0/0.5'` | `[0.0, 0.5]` | 0.25 | +0.25 | `0:2` | +1 | YES |
| `'-0.5/0'` | `[-0.5, -0.0]` | 0.25 | -0.25 | `-2:0` | -1 | YES |
| `'+0.5/0'` | `[0.5, 0.0]` | 0.25 | +0.25 | `0:2` | +1 | YES |
| `'-0.5'` | `[-0.5]` | 0.5 | -0.5 | `-2:-2` | -2 | YES |
| `'+0.5'` | `[0.5]` | 0.5 | +0.5 | `2:2` | +2 | YES |
| `'-0.5/1'` | `[-0.5, -1.0]` | 0.75 | -0.75 | `-4:-2` | -3 | YES |
| `'+0.5/1'` | `[0.5, 1.0]` | 0.75 | +0.75 | `2:4` | +3 | YES |
| `' -0/0.5 '` | `[-0.0, 0.5]` | 0.25 | **+0.25** | `-2:0` | **-1** | **NO** |
| `'-0/0.5 '` | `[-0.0, 0.5]` | 0.25 | **+0.25** | `-2:0` | **-1** | **NO** |
| `'-0 / 0.5'` | `[-0.0, 0.5]` | 0.25 | **+0.25** | `-2:0` | **-1** | **NO** |
| `'--0.5'` | `None`（拒绝） | – | – | **`2:2`** | **+2** | 规范**未拒绝** |
| `'+-0.5'` | `None`（拒绝） | – | – | `-2:-2` | -2 | 规范**未拒绝** |
| `''` / `None` / `'abc'` / `'1/2/3'` | `None`（拒绝） | – | – | `None`（拒绝） | – | 一致 |
| `'0'` | `[0.0]` | 0.0 | 0.0 | `0:0` | 0 | YES |
| `'-0'` | `[-0.0]` | 0.0 | 0.0 | `0:0` | 0 | YES（负号被吞但值相同） |
| `'+0'` | `[0.0]` | 0.0 | 0.0 | `0:0` | 0 | YES |
| `'2'` / `'2.5'` | `[2.0]` / `[2.5]` | 2.0 / 2.5 | 同 | `8:8` / `10:10` | 8 / 10 | YES |
| `'0.125'` | `[0.125]` | 0.125 | 0.125 | **`0:0`** | **0** | 规范**丢精度**（银行家舍入） |
| `'0.625'` | `[0.625]` | 0.625 | 0.625 | **`2:2`** | **2** | 规范**丢精度** |
| `'0.1'` | `[0.1]` | 0.1 | 0.1 | **`0:0`** | **0** | 规范**丢精度** |
| `'-1/+1'` | `[-1.0, 1.0]`（混合符号） | 1.0 | **0.0（中性）** | `-4:-4` | -4 | **NO** |
| `'inf'` / `'1e400'` | **`[inf]`（静默接受）** | inf | inf | **抛 OverflowError** | – | 两者都不可接受 |

### 3.1 负零风险（任务强制验证项）
- `float("-0")` → `-0.0`；`-0.0 < 0` → **False**（Python 语义）
- 因此 `events/line.py:10-11` 的 `y = -abs(y) if x<0 else abs(y)` 在首腿为 `-0` 时走 `else` 分支 → `"-0/0.5"` 的第二腿被赋 **正** 0.5 → 符号被翻转。**CODE + 实测**
- 真实数据中 `"-0/0.5"` 出现 **342 次**（ladder.txt）+ **12 次**（ladder_v7.txt）→ **DATA**，不是理论问题
- `parse_line_quarters` 通过"先剥符号、再把符号作用于全部腿"规避了此问题（`mapping/market.py:85-104`）→ **CODE**

### 3.2 等价关系（规范口径，`parse_line_quarters`）
| 写法对 | quarters | mid | 是否等价 |
|---|---|---|---|
| `"-0/0.5"` ≡ `"-0.5/0"` | `-2:0` | -1 | **等价**（同为 -0.25） |
| `"+0/0.5"` ≡ `"0/0.5"` ≡ `"+0.5/0"` | `0:2` | +1 | **等价**（同为 +0.25） |
| `"-0/0.5"` vs `"+0/0.5"` | `-2:0` vs `0:2` | -1 vs +1 | **不等价**（相差 0.5 球，跨盘） |
| `"-0.5/0"` vs `"0/0.5"` | `-2:0` vs `0:2` | -1 vs +1 | **不等价** |

→ 任务 Phase B 的核心问题 **"`-0/0.5` 与 `-0.5/0` 在既有规范下是否等价"** 答案：**等价**（`INFERENCE`，基于实测 quarters 一致）。
→ 候选实现实测 `compare_line("-0/0.5","-0.5/0")` → `CROSS/SIGN_FLIP/steps=2.0` → **假阳性**（CODE+实测）。

---

## 4. 候选实现与规范的差异（实测 52 条真实迁移）

脚本：`devcopy/.harness_tmp/verify_matrix.py` → 输出 `verify_matrix_output.txt`

| 规范分类 | 条数 | MAIN 标注 | 候选标注 |
|---|---|---|---|
| MAGNITUDE（幅度变化） | 24 | MAGNITUDE 24（100% 正确） | MAGNITUDE 22，**FLIP 2（假翻转）** |
| FLIP（跨盘） | 28 | MAGNITUDE 28（**0% 正确识别为翻转**） | **FLIP 18（64%）**，MAGNITUDE 10（漏判） |
| SAME（同一盘口） | 0 | – | – |

- **main 与候选在"是否产生事件"上完全一致：52/52 都 `changed=True`**（即两者都不会漏掉事件）
- 候选的 **12/52（23%）分类错误**：
  - **10 例漏判跨盘**：全部涉及 `"-0/0.5"`（伯恩茅斯 ×8、桑坦德竞技 ×2）
  - **2 例假翻转**：首尔FC `'-0/0.5' → '-1.5'`、`'-1.5' → '-0/0.5'`（规范为同侧幅度变化）
- **100% 的候选分类错误由单一根因造成**：`parse_line` 的 `-0` 符号丢失
- **同一市场变动在两侧被不同标注**（INFERENCE，实测证据见 `verify_claims_output.txt` C 节）：
  首尔FC `'-0/0.5'→'-1.5'` → 候选 `CROSS`；仁川联 `'+0/0.5'→'+1.5'` → 候选 `MAGNITUDE`

---

## 5. 既有契约与调用者影响

- **契约文本（GIT/TEST）**：`origin/phase1:tests/test_line.py:3-6` 明确
  `{changed: bool|None, direction: DEEPER/SHALLOWER/SAME/UNKNOWN, change_type: QUARTER_STEP/HALF_STEP/MULTI_STEP/SAME/UNKNOWN, steps}`
- **`CROSS`/`SIGN_FLIP` 在全部分支全历史中 0 命中**（Agent A：5 分支 `git grep` 均为 0；Agent D：`git log --all -S'CROSS'`/`-S'SIGN_FLIP'` 全空）
- **但"契约冲突"被夸大了**（Agent D CE6）：全仓库**没有任何代码读取** `line_direction`/`line_change_type` 的字面值，也无 DB CHECK 约束 → 新增词表**不会**破坏现有消费者；真正的风险是 `changed` 语义与 `steps` 量纲，不是词表本身
- **候选改变了 `changed` 的取值集合** → `LINE_CHANGE` **事件条数**会变化 → `replay/event_v1.py` 的 `event_count` 与 `replay_hash` 随之变化 → 回放行会重新插入而非去重（Agent D CE12）
- **`steps` 双量纲（CODE）**：幅度分支 `|Δdepth|/0.25`，CROSS 分支 `|Δvalue|/0.25`；`steps` 不落库（无该列），但任何未来消费方都会混淆

---

## 附录：源码原文（见文件后半部分）
=== main vs origin/phase1 diffstat ===
M	.gitignore
A	ACCEPTANCE_V0.1.md
A	ACCEPTANCE_V0.2.md
A	VERSION
A	backtest/engine_v1.py
A	backtest/engine_v2.py
A	cli.py
M	config/config.json
A	core/checks.py
M	core/collector.py
A	core/env.py
A	core/health.py
A	core/lock.py
M	core/log.py
M	core/status.py
M	database/db.py
M	decisions/engine_v1.py
A	decisions/plugin.py
A	decisions/plugins/__init__.py
A	decisions/plugins/candidate.py
A	docs/CI_REPORT.md
A	docs/INSTALL.md
A	docs/OPERATIONS.md
A	docs/RELEASE_NOTES.md
A	event/engine.py
M	events/engine_v3.py
M	events/group_v3.py
A	features/engine.py
M	features/engine_v2.py
M	main.py
M	mapping/__init__.py
A	mapping/audit.py
M	mapping/db.py
M	mapping/market.py
M	mapping/market_db.py
M	mapping/market_service.py
M	mapping/match.py
M	mapping/service.py
A	mapping/status.py
M	mapping/unified_db.py
M	mapping/unified_service.py
A	market/__init__.py
A	market/registry.py
A	market/selector.py
A	monitor/__init__.py
A	monitor/alert.py
M	monitor/monitor.py
A	monitor/watchlist.py
A	ops/backup.py
A	p2p/__init__.py
M	p2p/node.py
A	pipeline/__init__.py
A	pipeline/orchestrator.py
A	quality/__init__.py
A	quality/engine_v1.py
A	quality/errors.py
A	quality/validator.py
A	replay/engine.py
A	replay/engine_v2.py
A	replay/true_replay.py
A	requirements.txt
M	signals/engine_v1.py
A	signals/rules.py
M	sources/base.py
M	sources/bb.py
A	sources/contract.py
M	sources/registry.py
A	sources/sx.py
A	stability/__init__.py
A	stability/run.py
M	strategies/engine_v1.py
A	strategies/plugin.py
A	strategies/plugins/__init__.py
A	strategies/plugins/ah_multi_level_water.py
A	tests/_lock_helper.py
A	tests/conftest.py
A	tests/helpers.py
A	tests/test_audit_p0.py
A	tests/test_audit_p1.py
A	tests/test_audit_p2.py
---
d39c7aa 审计修复 P3: 一致性收口与文档
cec4853 审计修复 P2: 事务/连接/隔离/限速/超时
af2db46 审计修复 P1: 哈希噪声/盘口线同源/赔率基准/重试语义
e8c82d9 审计修复 P0: schema 兜底降级与 health_of 返回类型
4b9a1e8 Phase 13: 打包/文档/发布候选 (规格 §19 Phase 13)
---

=== events/line.py (main) ===
def parse_line(s):
    s=str(s).strip().replace(" ","")
    if not s:
        return None
    try:
        if "/" in s:
            a,b=s.split("/",1)
            x=float(a)
            y=float(b)
            if not b.startswith(("+","-")):
                y=-abs(y) if x<0 else abs(y)
            return [x,y]
        return [float(s)]
    except:
        return None


def norm(s):
    p=parse_line(s)
    if not p:
        return None

    return {
        "raw":str(s),
        "legs":p,
        "depth":sum(abs(x) for x in p)/len(p)
    }


def compare_line(old,new):
    a=norm(old)
    b=norm(new)

    if not a or not b:
        return {
            "changed":None,
            "direction":"UNKNOWN",
            "change_type":"UNKNOWN",
            "steps":None
        }

    x=a["depth"]
    y=b["depth"]

    if x==y:
        return {
            "changed":False,
            "direction":"SAME",
            "change_type":"SAME",
            "steps":0
        }

    if y>x:
        d="DEEPER"
    else:
        d="SHALLOWER"

    diff=abs(y-x)

    if diff==0.25:
        ct="QUARTER_STEP"
    elif diff==0.5:
        ct="HALF_STEP"
    else:
        ct="MULTI_STEP"

    return {
        "changed":True,
        "direction":d,
        "change_type":ct,
        "steps":diff/0.25
    }


if __name__=="__main__":
    tests=[
        ("-0.5","-0.75"),
        ("-1","-1/1.5"),
        ("-1/1.5","-1"),
        ("+0.5","+0.25"),
        ("+0.25","+0.5"),
        ("0","-0.5"),
        ("-0.5","0"),
        ("0.5","0/0.5"),
        ("0/0.5","0.5"),
        ("1","1/1.5"),
        ("1/1.5","1"),
    ]

    print("=== Asian Line Parser V3.3 ===")

    for old,new in tests:
        r=compare_line(old,new)
        print(
            old,"→",new,
            "|",r
        )

=== mapping/market.py (main) ===

from dataclasses import dataclass

@dataclass
class MarketMapping:
    source: str
    source_market_id: str
    bookmaker: str | None
    source_match_id: str | None
    market_type: str
    period: str | None
    line_raw: str | None
    line: float | None
    side: str | None
    option: str
    odds: float | None

MTY = {
    "1000": "asian_handicap",
    "1007": "over_under",
    "1005": "1x2",
    "1012": "double_chance",
    "1010": "corner_over_under",
}

PE = {
    "1001": "full_time",
}

def parse_line(v):
    if v is None:
        return None

    s = str(v).strip()

    try:
        return float(s)
    except ValueError:
        pass

    if "/" in s:
        p = s.split("/")
        try:
            return (float(p[0]) + float(p[1])) / 2
        except ValueError:
            return None

    return None

def detect_side(option, home, away):
    if option == home:
        return "home"
    if option == away:
        return "away"
    return None

def normalize(record):
    mtype = MTY.get(str(record.market_type), "unknown")
    period = PE.get(str(record.period), str(record.period) if record.period else None)

    side = detect_side(
        record.option,
        record.home,
        record.away
    )

    line = record.line

    if line is None:
        line = parse_line(record.line_raw)

    return MarketMapping(
        source=record.source,
        source_market_id=record.source_market_id,
        bookmaker=record.bookmaker,
        source_match_id=record.source_match_id,
        market_type=mtype,
        period=period,
        line_raw=record.line_raw,
        line=line,
        side=side,
        option=record.option,
        odds=record.odds
    )

=== events/group_v3.py (main) ===

import sqlite3,hashlib
c=sqlite3.connect("data/bb.db");c.row_factory=sqlite3.Row

c.execute("""create table if not exists event_groups_v3(
id integer primary key,canonical_match_id text,source text,
market_type text,period text,old_time integer,new_time integer,
group_type text,event_count integer,detail text,group_hash text unique)""")

def depth(s):
 try:
  s=str(s or "").replace(" ","")
  if "/" in s:
   a,b=s.split("/",1)
   return round((abs(float(a))+abs(float(b)))/2,4)
  return abs(float(s))
 except:return None

rows=c.execute("select * from events_v3 order by new_time,id").fetchall()
gs={}
for r in rows:
 d=None if r["market_type"]=="1x2" else depth(r["old_line_raw"])
 k=(r["canonical_match_id"],r["source"],r["market_type"],
    r["period"],r["old_time"],r["new_time"],d)
 gs.setdefault(k,[]).append(r)

n=0
for k,rs in gs.items():
 ups=sum(r["odds_direction"]=="UP" for r in rs)
 downs=sum(r["odds_direction"]=="DOWN" for r in rs)
 lines=[r for r in rs if r["event_type"]=="LINE_CHANGE"]

 typ=None
 if lines and (ups or downs):
  typ="LINE_WATER"
 elif ups and downs:
  typ="WATER_SHIFT"

 if not typ:continue

 detail=";".join(
  "%s:%s>%s"%(r["option"],r["old_line_raw"],r["new_line_raw"])
  if r["event_type"]=="LINE_CHANGE"
  else "%s:%s>%s"%(r["option"],r["old_odds"],r["new_odds"])
  for r in rs)

 h=hashlib.sha256(repr((k,typ,detail)).encode()).hexdigest()
 x=c.execute("""insert or ignore into event_groups_v3
(canonical_match_id,source,market_type,period,old_time,new_time,
group_type,event_count,detail,group_hash)
values(?,?,?,?,?,?,?,?,?,?)""",
(k[0],k[1],k[2],k[3],k[4],k[5],typ,len(rs),detail,h))
 n+=x.rowcount

c.commit()
print("新增GROUP",n)
for r in c.execute("""select market_type,group_type,count(*)
from event_groups_v3 group by market_type,group_type"""):
 print(*r)
c.close()

=== mainline_v4/v5/v6 (main) ===

---v4---
exec(open("mainline_v3.py").read().split("R=[]")[0])
R=[]
def dep(s):
 p=str(s).replace("+","")
 if "/" in p:
  a,b=p.split("/")
  x=float(a);y=float(b)
  if y and abs(y)<abs(x): y=x
  return (abs(x)+abs(y))/2
 return abs(float(p))
for mid,v in H.items():
 v.sort()
 for i in range(len(v)-1):
  a=v[i][1];b=v[i+1][1]
  if a[1]==b[1]: continue
  fut=[x[1][1] for x in v[i+1:i+5]]
  n=fut.count(b[1])
  if n<3 or a[1] in fut: continue
  d1=dep(a[1]);d2=dep(b[1])
  direction="DEEPER" if d2>d1 else "SHALLOWER"
  R.append((mid,a[0],a[1],round(a[3],2),round(a[4],2),
            b[0],b[1],round(b[3],2),round(b[4],2),direction,n))
for x in R: print(*x)
print("=== STAT ===")
print("REAL",len(R))
print("DEEPER",sum(x[-2]=="DEEPER" for x in R))
print("SHALLOWER",sum(x[-2]=="SHALLOWER" for x in R))

---v5---
exec(open("mainline_v3.py").read().split("R=[]")[0])

def eq(x):
 return abs(x[3]-1.95)+abs(x[4]-1.95)

def depth(s):
 p=str(s).replace("+","")
 if "/" in p:
  a,b=p.split("/")
  a=float(a);b=float(b)
  if not str(p.split("/")[1]).startswith(("+","-")): b=-abs(b) if a<0 else abs(b)
  return (abs(a)+abs(b))/2
 return abs(float(p))

R=[]
for mid,v in H.items():
 v.sort()
 lines=[x[1][1] for x in v]
 for i in range(len(v)-1):
  a=v[i][1];b=v[i+1][1]
  if a[1]==b[1]: continue
  fut=lines[i+1:i+6]
  n=fut.count(b[1])
  if not n: continue
  back=a[1] in fut
  later=fut[1:] if len(fut)>1 else []
  stable=later.count(b[1])>=2
  oscill=back and b[1] in later
  ed=eq(a);ne=eq(b)
  if oscill:
   typ="OSCILLATION"
  elif stable and ne<=0.30:
   typ="CONFIRMED"
  else:
   typ="LIKELY"
  di="DEEPER" if depth(b[1])>depth(a[1]) else "SHALLOWER"
  R.append((mid,a[0],a[1],round(ed,2),b[0],b[1],round(ne,2),di,n,typ))
for x in R: print(*x)
print("=== STAT ===")
for k in ["CONFIRMED","LIKELY","OSCILLATION"]:
 print(k,sum(x[-1]==k for x in R))
print("TOTAL",len(R))

---v6---
exec(open("mainline_v3.py").read().split("R=[]")[0])

def eq(x):
 return abs(x[3]-1.95)+abs(x[4]-1.95)

def depth(s):
 p=str(s).replace("+","")
 if "/" in p:
  a,b=p.split("/")
  a=float(a);b=float(b)
  if not str(p.split("/")[1]).startswith(("+","-")): b=-abs(b) if a<0 else abs(b)
  return (abs(a)+abs(b))/2
 return abs(float(p))

R=[]
for mid,v in H.items():
 v.sort()
 lines=[x[1][1] for x in v]
 for i in range(len(v)-1):
  a=v[i][1];b=v[i+1][1]
  if a[1]==b[1]: continue
  fut=lines[i+1:i+11]
  if len(fut)<5: typ="EDGE"
  else:
   nb=fut.count(b[1]); oa=fut.count(a[1])
   first_old=next((j for j,x in enumerate(fut) if x==a[1]),99)
   first_new=next((j for j,x in enumerate(fut) if x==b[1]),99)
   if oa>0 and first_old<8:
    typ="OSCILLATION"
   elif nb>=7 and oa==0 and eq(b)<=0.30:
    typ="CONFIRMED"
   else:
    typ="LIKELY"
  di="DEEPER" if depth(b[1])>depth(a[1]) else "SHALLOWER"
  R.append((mid,a[0],a[1],b[0],b[1],di,typ))
for x in R: print(*x)
print("=== STAT ===")
for k in ["CONFIRMED","LIKELY","OSCILLATION","EDGE"]:
 print(k,sum(x[-1]==k for x in R))
print("TOTAL",len(R))

=== events/line.py (devcopy/BB-D1 candidate) ===

def parse_line(s):
    s=str(s).strip().replace(" ","")
    if not s:
        return None
    try:
        if "/" in s:
            a,b=s.split("/",1)
            x=float(a)
            y=float(b)
            if not b.startswith(("+","-")):
                y=-abs(y) if x<0 else abs(y)
            return [x,y]
        return [float(s)]
    except:
        return None


def norm(s):
    p=parse_line(s)
    if not p:
        return None

    return {
        "raw":str(s),
        "legs":p,
        "depth":sum(abs(x) for x in p)/len(p),
        "value":sum(p)/len(p)
    }


EPS=1e-9


def _eq(a,b):
    return abs(a-b)<=EPS


def _polar(v):
    # +1 positive, -1 negative, 0 neutral (a value of 0 carries no polarity)
    if abs(v)<=EPS:
        return 0
    return 1 if v>0 else -1


def compare_line(old,new):
    a=norm(old)
    b=norm(new)

    if not a or not b:
        return {
            "changed":None,
            "direction":"UNKNOWN",
            "change_type":"UNKNOWN",
            "steps":None
        }

    x=a["depth"]
    y=b["depth"]
    vo=a["value"]
    vn=b["value"]

    # unchanged only when the depth matches exactly (as the original did)
    # AND the signed value matches (small tolerance, float noise only)
    if x==y and _eq(vo,vn):
        return {
            "changed":False,
            "direction":"SAME",
            "change_type":"SAME",
            "steps":0
        }

    # crossed the money: opposite signs and neither side neutral (0)
    po=_polar(vo)
    pn=_polar(vn)
    if po and pn and po!=pn:
        return {
            "changed":True,
            "direction":"CROSS",
            "change_type":"SIGN_FLIP",
            "steps":round(abs(vn-vo)/0.25,4)
        }

    if y>x:
        d="DEEPER"
    else:
        d="SHALLOWER"

    diff=abs(y-x)

    if diff==0.25:
        ct="QUARTER_STEP"
    elif diff==0.5:
        ct="HALF_STEP"
    else:
        ct="MULTI_STEP"

    return {
        "changed":True,
        "direction":d,
        "change_type":ct,
        "steps":diff/0.25
    }


if __name__=="__main__":
    tests=[
        ("-0.5","-0.75"),
        ("-1","-1/1.5"),
        ("-1/1.5","-1"),
        ("+0.5","+0.25"),
        ("+0.25","+0.5"),
        ("0","-0.5"),
        ("-0.5","0"),
        ("0.5","0/0.5"),
        ("0/0.5","0.5"),
        ("1","1/1.5"),
        ("1/1.5","1"),
    ]
    flip_tests=[
        ("-0.5","+0.5"),
        ("0.5","-0.5"),
        ("-0.25","+0.25"),
        ("-1/1.5","+1/1.5"),
    ]
    same_tests=[
        ("-0.5","-0.50"),
        ("0","0.0"),
        ("-1/1.5","-1.25"),
        ("0/0.5","0/0.50"),
    ]

    print("=== Asian Line Parser V3.3 ===")

    for old,new in tests:
        r=compare_line(old,new)
        print(
            old,"→",new,
            "|",r
        )

    print("--- sign flip ---")
    for old,new in flip_tests:
        r=compare_line(old,new)
        print(old,"→",new,"|",r)
        assert r["changed"] is True
        assert r["direction"]=="CROSS"
        assert r["change_type"]=="SIGN_FLIP"

    print("--- equivalent spelling ---")
    for old,new in same_tests:
        r=compare_line(old,new)
        print(old,"→",new,"|",r)
        assert r["changed"] is False
        assert r["direction"]=="SAME"
        assert r["change_type"]=="SAME"
        assert r["steps"]==0

    print("OK")
