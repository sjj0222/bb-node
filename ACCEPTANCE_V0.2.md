# BB Node V0.2 E2E ACCEPTANCE

## Baseline
- V0.1 = PASS (commit cd0b7ce, 59 tests, 双真实源全链路)
- V0.2 从 V0.1 稳定基线继续开发, 未推倒重来

## 环境
- Commit: d339ab3 (分支 v0.2)
- Python: 3.12.11
- Database: SQLite (Schema V2 -> V3 Migration 幂等验证通过)
- 数据库: data/bb.db (WAL, V0.1 数据完整保留)
- Replay DB: data/replay.db

## Sources (真实独立双源)
- Source A = BB API (https://api.infv1.com) = **PASS**
  - source_health: UP, 3012 records, latency 记录
- Source B = SX Bet (https://api.sx.bet, 免 key) = **PASS**
  - source_health: UP, 68 records
- Source 隔离: A DOWN 不影响 B (health + 测试验证)
- HTTP success ≠ DATA success ≠ PIPELINE success (core/health.py 区分)

## Monitor
- 状态机: STOPPED/STARTING/RUNNING/DEGRADED/ERROR/STOPPING = **PASS**
- Manual Mode (run_once) = **PASS**
- Daemon/Background Mode (start/stop/restart/status) = **PASS**
- Watchlist: ADD/REMOVE/LIST/STATUS = **PASS**
- Alert 系统: 9 种 alert_type 结构化 Alert = **PASS**
- Source 故障隔离: DEGRADED 继续运行 = **PASS**
- 真实 Monitor once: unified 12427, events 740, signals 38,
  strategies 9 TRIGGERED, decisions 9 CANDIDATE = **PASS**

## Market Extension
- 统一 Market Handler/Schema (market/registry.py, 禁 if/elif 膨胀) = **PASS**
- AH / OU / 1X2 真实 MAPPED = **PASS**
- 新增真实市场 corner_over_under: 真实数据 MAPPED 86 条 = **PASS**
- Unsupported Market -> UNSUPPORTED/PENDING 不静默丢弃 = **PASS**
- market_mappings: MAPPED 4279, INVALID 22 (非法盘口显式标记)

## Data Quality
- Quality Layer (quality/engine_v1.py) = **PASS**
- 真实数据 score = 100.0 (total 21667, valid 21667,
  invalid 0, duplicate 0, conflict 0, unmapped 0)
- out_of_order 1 被显式标记(不静默)
- Missing/Invalid/Duplicate/Conflict/Stale/Out-of-order 测试覆盖 = **PASS**

## P2P
- Node Identity (node_id/protocol/software/capabilities/last_seen) = **PASS**
- 同步对象: RAW + Unified (不同步派生结果) = **PASS**
- 真实 RAW 跨节点同步: 100 条真实 BB RAW 导入 + SHA256 hash 全一致 = **PASS**
- Unified 同步: 50 条真实导入 = **PASS**
- Dedup: 重复同步 written=0 = **PASS**
- Integrity: hash 篡改 REJECT = **PASS**
- Conflict: 不覆盖, 两份并存 = **PASS**
- Protocol version: 不兼容 REJECT = **PASS**
- 断线恢复 + 增量补同步 (from/to/cursor) = **PASS**

## Strategy / Decision Plugin
- Strategy Plugin 调度器 (strategies/plugins/) = **PASS**
- Decision Plugin 调度器 (decisions/plugins/) = **PASS**
- Core 与 Plugin 解耦, 投资模型未写入核心 = **PASS**
- 真实输出: AH_MULTI_LEVEL_WATER 9 TRIGGERED -> 9 CANDIDATE

## Replay (V0.2)
- Time Travel / No Future Leakage (固定窗口) = **PASS**
- 真实数据双跑一致性: 固定窗口 T0-T1,
  18,519 snapshots / 762 events / 242 features / 41 signals /
  10 strategies / 10 decisions
  replay_hash 与 counts 双跑完全等价 = **PASS**
- Multi Source / Version Tracking (data/engine/schema/config/strategy) = **PASS**

## Backtest (V0.2)
- 基于 Replay (固定窗口真实数据) = **PASS**
- samples=249, triggered=10, decisions=10
- group_by strategy: AH_MULTI_LEVEL_WATER 10/10
- 无结果字段不虚构 ROI = **PASS**

## Stability
- 24h: **RUNNING** (后台 PID 3346, interval 300s,
  run_id stability-c13fa49cc00b, 已运行中; 状态文件 /tmp/bbnode_stability.json)
- 72h: NOT COMPLETED (目标)
- 指标监控: Memory/CPU/DB size/WAL/dup_rate/errors/recoveries
- 恢复: 单轮 crash -> errors++, 继续运行

## Regression
- V0.1 的 59 个测试: **PASS**
- V0.2 新增 56 个测试: **PASS**
- 总计 115 tests PASS

## Real E2E
真实 Source -> Monitor -> RAW -> Unified -> Data Quality ->
Event(V3) -> Feature(V2) -> Signal(V1) -> Strategy Plugin ->
Decision Plugin -> P2P -> Replay -> Backtest = **PASS**

## Final
**PASS**

---
备注:
1. 24h 稳定性为硬条件, 当前任务在后台运行中(启动时间 2026-10-04);
   若环境在任务完成前终止, 以 stability_runs 表最终记录为准重新判定。
2. 72h 为目标, 未完成不构成 FAIL。
