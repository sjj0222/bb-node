# 04_REAL_DATA_EVIDENCE.md

> 数据来源：**仅仓库内已跟踪文件**。仓库外原始 CSV（`~/odds_data/snapshots/*.csv`，见 `ladder_check.py:7`、`ladder_v7.py:7`、`line_v4.py:3`、`scan_lines.py:3`、`check_candidates.py:3`）**在本环境不可访问，本次未读取、未伪造**。
> 所有统计由 `devcopy/.harness_tmp/verify_claims.py`（只读，`PYTHONDONTWRITEBYTECODE=1`，cwd=/tmp）产出，输出见 `verify_claims_output.txt` / `verify_matrix_output.txt`。

---

## 1. 数据集构成

| 文件 | 规模 | 产生方式 | 内容 |
|---|---|---|---|
| `ladder.txt` | 1735 行 / 3470 个选项行 / 128 个 (match, market_id, option) 序列 | `ladder_check.py`（按快照/比赛/档位逐行导出 `option:line:odds`） | 每行 = 一个快照时刻的一个 market 的两选项报价 |
| `ladder_v7.txt` | 156 行 / **26** 个 `MARKET_CHANGE` 块 | `ladder_v7.py`（**仅**在 market_id 集合变化时输出） | 旧/新档位集合 + 每个变动档位的两选项 line+odds |

**选样偏差（DATA，重要）**：
- `ladder.txt` **完全不含盘口变化**：128 个 (match, market_id, option) 序列中，**line 取值集合 >1 的序列数 = 0**（实测）。它是"同档位报价随赔率漂移"的快照，不是盘口变化数据。
- `ladder_v7.txt` **只含档位集合变化事件**，且每次变化恰好一个旧档位消失 + 一个新档位出现（26/26）。
- 两者**都不是**"同一盘口跨时间变化"的完整时间序列 → **现有仓库数据无法回答"某一方在同一次市场调整中盘口怎么变"以外的问题**。

---

## 2. 盘口写法分布（全部实测）

`ladder.txt` 全部线串（19 种，按出现次数）：

| 次数 | 写法 | 次数 | 写法 |
|---|---|---|---|
| 424 | `0` | 342 | `+0/0.5` |
| 342 | `-0/0.5` | 318 | `+0.5` |
| 318 | `-0.5` | 255 | `+0.5/1` |
| 255 | `-0.5/1` | 213 | `+1` |
| 213 | `-1` | 79 | `+1/1.5` |
| 79 | `-1/1.5` | 56 | `±2/2.5`, `±2.5/3`, `±2.5`, `±2` |
| 56 | `+2/2.5` | 56 | `+2.5/3` |
| 56 | `+2.5` | 56 | `+2` |
| 51 | `±3` | 27 | `±1.5` |
| 27 | `-1.5` | 14 | `±1.5/2` |

**关键事实（DATA）**：
| 目标写法 | ladder.txt | ladder_v7.txt | 结论 |
|---|---|---|---|
| `"-0/0.5"` | **342** | **12** | 真实高频形态 |
| `"+0/0.5"` | **342** | **12** | 真实高频形态 |
| `"-0.5/1"` | 255 | 4 | 存在 |
| `"+0.5/1"` | 255 | 4 | 存在 |
| `"0/0.5"`（首腿无符号） | **0**（锚定正则 `[: ,]0/0\.5`） | **0** | **真实数据中不存在** |
| `"-0.5/0"` | **0** | **0** | **真实数据中不存在** |
| `"+0.5/0"` | **0** | **0** | **真实数据中不存在** |

→ 负零族（`"-0/0.5"`）**占全部盘口行的 9.9%**（342/3470），是最常见的分盘形态之一。**负零处理不是理论问题。**

→ 真实数据的分盘**腿序恒为升序**（`0/0.5`、`0.5/1`、`1/1.5`、`1.5/2`、`2/2.5`、`2.5/3`），**第二腿从不带独立符号** → `parse_line_quarters` 的"符号整行生效"规则与真实数据完全吻合；`parse_line` 的"二腿继承首腿"也吻合，**但首腿为 `-0` 时失效**。

---

## 3. 52 条真实盘口迁移 vs 三种判定口径（实测）

迁移来源：`ladder_v7.txt` 的 26 个 `MARKET_CHANGE` 块 → 每个块按选项配对出 2 条（消失档位的 option → 出现档位的同 option）= **52 条**。
口径定义：
- **SPEC** = `origin/phase1:mapping/market.py:parse_line_quarters`：`quarters` 相同 ⇒ SAME；`mid` 异号且非 0 ⇒ FLIP；否则 MAGNITUDE
- **MAIN** = `main:events/line.py:compare_line`（只有 SAME / 幅度）
- **CAND** = `devcopy:events/line.py:compare_line`（多 CROSS）

| SPEC 分类 | 条数 | MAIN | CAND |
|---|---|---|---|
| SAME | 0 | – | – |
| MAGNITUDE | 24 | MAGNITUDE 24（**100% 正确**） | MAGNITUDE 22 / **FLIP 2（假翻转）** |
| FLIP | 28 | **MAGNITUDE 28（0% 识别为翻转）** | **FLIP 18（64%）/ MAGNITUDE 10（漏判）** |

- **是否产生事件**：MAIN 52/52 `changed=True`，CAND 52/52 `changed=True` → **两者在"有无事件"上完全一致**，差别只在标签
- **候选 12/52（23%）标签错误**，**全部**由 `"-0/0.5"` 引起：
  - 漏判跨盘 10 条：伯恩茅斯 `'+1'↔'-0/0.5'`（8 条）、桑坦德竞技 `'-0/0.5'→'+1'`（2 条）
  - 假翻转 2 条：首尔FC `'-0/0.5'→'-1.5'`、`'-1.5'→'-0/0.5'`（规范判为同侧幅度变化）
- **同一市场变动两侧标注不一致**：首尔FC `'-0/0.5'→'-1.5'` → CAND `CROSS`；仁川联 `'+0/0.5'→'+1.5'` → CAND `MAGNITUDE`

### 3.1 变化幅度分布（按规范口径）
| 类型 | 条数 | 典型 |
|---|---|---|
| 等深异号翻转（BB-D1 的目标形态） | **0** | — |
| 跨盘但深度也变 | 28 | `'-1'→'+0/0.5'`、`'+0.5/1'→'-0.5'` |
| 同侧幅度变化 | 24 | `'-1/1.5'→'0'`、`'-1.5/2'→'-0.5'`、`'-1.5/2'→'-3'` |

→ **"等深异号翻转"在现有全部真实数据中出现 0 次**。BB-D1 的原始目标形态**缺乏实证支撑**（DATA）。

---

## 4. 覆盖范围与必须补充的数据

**本数据集能证明**：负零分盘高频存在；真实数据只用升序腿序、二腿不带符号；`market_id` 标识报价档位且会轮播更换；档位集合变化是"市场调整"的可观测代理；52 条真实迁移的分类正确性可逐条量化。

**本数据集不能证明（UNKNOWN）**：
1. 同一盘口（同一档位）跨快照的连续变化序列 —— `ladder.txt` 恒定、`ladder_v7.txt` 只记集合变化
2. 盘口变化时 **`pe`（周期）、`option_index`、精确 `received_at`** —— 抽取时已丢弃
3. `mty` 以外的盘口类型（大小球 `1007`、角球 `1010` 等）的线值形态 —— 抽取时过滤了 `mty=='1000'`
4. 第二数据源（上游 `sx`，mty `"3"`）的线值写法 —— 本仓库无其样本
5. 原始 CSV 全文（**本次未访问**）

**最小补充证据需求**：
- 提供 `~/odds_data/snapshots/*.csv`（或等价导出）**至少包含**：`match_id, mty, pe, market_id, option, option_index, line, odds, home, away, received_at`
- 覆盖**全部 mty**（不只 `1000`）与**至少 2 个来源**
- 覆盖**连续多个快照**，以便重建"同一 (match, mty, pe, option_index) 的 line 序列"（这才是 `scan_lines.py:6` 的口径，也是判定"等深异号翻转"是否真实存在所需的最小数据）

---

## 5. 静态统计的可复核性

| 统计 | 复核命令 | 输出文件 |
|---|---|---|
| 线串分布 | `tr ',' '\n' < ladder.txt \| sed 's/^[^:]*://' \| sed 's/:[0-9.]*$//' \| sort \| uniq -c \| sort -rn` | `04_REAL_DATA_EVIDENCE.md` §2 |
| 无符号 `0/0.5` | `grep -cE '[: ,]0/0\.5' ladder.txt ladder_v7.txt` → 0/0 | 同上 |
| `-0.5/0` / `+0.5/0` | `grep -c -- "-0.5/0" …` → 0/0 | 同上 |
| 52 条迁移 + 三方混淆矩阵 | `PYTHONDONTWRITEBYTECODE=1 python3 devcopy/.harness_tmp/verify_matrix.py` | `verify_matrix_output.txt` |
| 边界值矩阵 | `PYTHONDONTWRITEBYTECODE=1 python3 devcopy/.harness_tmp/verify_boundary.py` | `verify_boundary_output.txt` |
| ladder.txt 零变化 | `PYTHONDONTWRITEBYTECODE=1 python3 devcopy/.harness_tmp/verify_claims.py` A 节 | `verify_claims_output.txt` |
