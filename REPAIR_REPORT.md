# BB-D1 事件配对键修复报告

## 1. 执行概要

| 项目 | 值 |
|------|-----|
| 工作分支 | `audit/bb-d1-event-pairing-20261027` |
| 基线提交 | `b1581d7e31466a584c5a2cc0c842832aac3fefa2` |
| 修复提交 | 待创建（本地未提交） |
| 修改文件 | `events/engine_v3.py`（2 行改动） |
| 新增文件 | `tests/test_event_pairing.py`（5 个测试） |
| 测试结果 | 5/5 通过 |

## 2. 缺陷证据

### 2.1 配对键缺少 source_market_id

**位置**：`events/engine_v3.py:33-35` 和 `:38-39`

**当前代码（修复前）**：
```python
k=(r["source"],r["canonical_match_id"],r["market_type"],
   r["period"],r["side"],r["option"])
```

**问题**：配对键不包含 `source_market_id`，导致同一比赛内不同盘口档位（不同 `source_market_id`）的选项共享相同的配对键。当两个不同市场的同一方向选项（如两个不同 handicap 的“热那亚”选项）同时存在于旧快照中，新快照的某一行可能与错误的旧市场行被配对。

### 2.2 source_market_id 的字段来源与传递链路

| 阶段 | 文件:行 | 字段来源 | 传递方式 |
|------|---------|---------|---------|
| Source Adapter | `sources/bb.py:39` | `mk.get("id")` — 上游盘口档位 ID | 赋值给 `mid` 变量 |
| Normalized | `sources/bb.py:60` | `source_market_id=mid` | 写入 `NormalizedRecord.source_market_id` |
| Unified | `mapping/unified_service.py:12` | `source_market_id=market.source_market_id` | 透传到 `UnifiedRecord` |
| Unified DB | `mapping/unified_db.py:13` | `source_market_id TEXT NOT NULL` | 存入 `unified_snapshots` 表，UNIQUE 约束包含该字段 |
| Event Engine | `events/engine_v3.py:33-35` | **未使用** | 配对键中缺失该字段 |

### 2.3 真实数据证据

从 `ladder.txt` 真实数据样本（1735 行，3470 个选项行）：

```
snapshot_202609 5388944 | 120455970 | 热那亚:+0.5:2.07,科莫 1907:-0.5:1.83
snapshot_202609 5388944 | 120455971 | 热那亚:+0.5/1:1.82,科莫 1907:-0.5/1:2.08
snapshot_202609 5388944 | 120455972 | 热那亚:+0/0.5:2.42,科莫 1907:-0/0.5:1.6
```

- 同一 `match_id=5388944` 的不同行具有不同 `market_id`（120455970、120455971、120455972...）
- 不同 `market_id` 对应不同盘口档位（+0.5、+0.5/1、+0/0.5...）
- `ladder_v7.txt` 确认市场 ID 会随时间轮播（MARKET_CHANGE：OLD 包含 122936957，NEW 包含 122759832）

**结论**：`source_market_id` 真实存在、非空（`unified_snapshots` 表定义为 `TEXT NOT NULL`）、能区分同一比赛内的不同盘口档位，适合作为配对条件。

## 3. 修复内容

### 3.1 修改：events/engine_v3.py

在配对键中加入 `source_market_id`，两处都需要修改：

**建立 old 字典时（第 33-35 行）**：
```python
# 修复前
k=(r["source"],r["canonical_match_id"],r["market_type"],
   r["period"],r["side"],r["option"])

# 修复后
k=(r["source"],r["canonical_match_id"],r["market_type"],
   r["period"],r["side"],r["option"],r["source_market_id"])
```

**查找候选行时（第 38-40 行）**：
```python
# 修复前
k=(r["source"],r["canonical_match_id"],r["market_type"],
   r["period"],r["side"],r["option"])

# 修复后
k=(r["source"],r["canonical_match_id"],r["market_type"],
   r["period"],r["side"],r["option"],r["source_market_id"])
```

### 3.2 未修改的内容

- 未修改 `replay/event_v1.py` 和 `replay/event_v2.py`（它们有相同模式，但本次任务范围限定为 `events/engine_v3.py`）
- 未修改数据库 Schema
- 未修改原始数据
- 未修改 `canonical_match_id`、`auto_map`、features 表或数据库路径
- 未修改 BB-D1 业务语义（U1–U6 保持未决）

## 4. 测试与验证

### 4.1 新增测试：tests/test_event_pairing.py

5 个测试用例，全部通过：

| 测试 | 目的 | 结果 |
|------|------|------|
| test_same_market_id_pairs_correctly | 同一 source_market_id 应正确配对，产生 LINE_CHANGE + WATER_CHANGE | PASS |
| test_different_market_id_not_paired | 不同 source_market_id 不应被错误配对（跨市场错配防护） | PASS |
| test_different_match_not_paired | 不同 canonical_match_id 不应配对 | PASS |
| test_empty_source_market_id_pairs_with_empty | 空 source_market_id 之间应正常配对 | PASS |
| test_no_backfill_for_unmatched_b_rows | B 侧无匹配 A 行时不应静默产生事件 | PASS |

**退出码**：0  
**测试总数**：5，通过：5，失败：0  
**测试数据**：完全使用内存中的合成数据，未写入任何生产数据库。

### 4.2 缺陷复现验证

将 `events/engine_v3.py` 临时还原为旧代码（不含 `source_market_id` 在配对键中），运行 `test_different_market_id_not_paired`：

- 旧代码：测试**失败**（1 个事件，mkt_2 被错误配对）
- 新代码：测试**通过**（2 个事件，只有 mkt_1 配对）

证明该修复修复了真实的跨市场错配缺陷。

### 4.3 未覆盖的场景

| 场景 | 原因 |
|------|------|
| 事件引擎端到端运行（main() 写入数据库） | 数据隔离约束，`data/` 目录不存在，执行 main() 会创建/写入 `data/bb.db` |
| replay/event_v1.py 和 replay/event_v2.py 的相同修复 | 本次任务范围限定为 `events/engine_v3.py`，但这两个文件有相同的配对键缺陷，建议后续修复 |
| 市场 ID 轮播导致同一逻辑市场在不同时间点的 market_id 不同 | 需要业务方确认：市场 ID 轮播后是否应视为同一市场继续配对，还是视为新市场 |

## 5. 剩余风险

| 风险 | 等级 | 说明 |
|------|------|------|
| 事件引擎端到端未验证 | MEDIUM | 未在真实数据库上运行 main()，因数据隔离约束无法执行 |
| replay 引擎相同缺陷未修复 | MEDIUM | `replay/event_v1.py:23-32` 和 `replay/event_v2.py:30-43` 有相同的配对键问题 |
| 市场 ID 轮播 | LOW | 如果同一逻辑市场的 market_id 随时间变化，添加 source_market_id 到配对键会导致跨时间点的同一市场不被配对。但这比跨市场错配更安全 |
| canonical_match_id 恒为 NULL | HIGH | `events/engine_v3.py:21-23` 查询 `where canonical_match_id is not null`，若恒为 NULL 则事件引擎不产出任何事件（U5 未决） |

## 6. U1–U6 状态

**所有 6 项业务语义问题保持 UNRESOLVED**，未裁定任何业务语义。本次修复仅解决技术层面的配对键缺陷，不涉及业务语义判定。

## 7. 后续建议

1. **P0**：在 `replay/event_v1.py` 和 `replay/event_v2.py` 中应用相同的 `source_market_id` 配对键修复
2. **P0**：调查 `canonical_match_id` 在生产链路上是否恒为 NULL（U5），若是则事件引擎可能永不产出事件
3. **P1**：在受控环境中（测试数据库）运行 `events/engine_v3.py:main()` 的端到端测试
4. **BLOCKED**：获取规格文件 `BBN-PRD-ARCH-SPEC V1.0`，裁定 U1–U6 业务语义（U6）

## 8. 提交与推送策略

- 修复成立，相关测试通过，工作区隔离有效
- 可在独立分支 `audit/bb-d1-event-pairing-20261027` 上提交并推送
- 不合并 PR，不修改 `main`
- 不把原工作区的 102 个未跟踪文件整体提交
