# BB Node V0.1 FINAL ACCEPTANCE

**Commit:** cd0b7ce (main)
**Environment:** Linux (Doubao Agent VM), Python 3.12.11, requests 2.34.2, pytest 7.x
**Database:** SQLite data/bb.db (WAL + FK, schema_version=2, 20 tables), data/replay.db (隔离 Replay 库)

---

## Sources（规则 51-1/3）

| Source | 真实 | 采集轮次 | unified 行数 | 状态 |
|---|---|---|---|---|
| Source A = BB (api.infv1.com) | ✓ 真实 API（MD5 签名） | 5 | 9018 | **PASS** |
| Source B = SX Bet (api.sx.bet, 免 key) | ✓ 真实 API（orderbook-v3） | 5 | 312 | **PASS** |

- 独立 Adapter / RAW / Source ID / 错误隔离（规则 3.2/3.3）：一个 Source 故障不拖垮另一个（tests/test_failure.py::test_source_down_isolated）
- BB 当前赛历无 8 大联赛 → leagues 配置 `{}` 全量采集真实数据（真实数据优先，规则 3.1）

## Pipeline（真实 E2E，规则 37/51-18）

| Stage | 结果 | 说明 |
|---|---|---|
| COLLECT | **PASS** | 10 次 collection_runs 全部 success（BB 5 + SX 5） |
| RAW | **PASS** | 原样保存（JSON + sha256 data_hash，去重），不可变 |
| NORMALIZED | **PASS** | 双源统一为 NormalizedRecord（源格式类型由 market.py 统一映射） |
| MAPPING | **PASS** | match/market 显式状态：MAPPED 9330 / UNMAPPED / INVALID 显式记录 |
| UNIFIED | **PASS** | 9330 行（bb 9018 + sx 312），下游唯一标准入口 |
| EVENT | **PASS** | 183 事件（LINE_CHANGE 6 + WATER_CHANGE 177），按 source 分组时间窗，乱序安全 |
| FEATURE | **PASS** | 86 特征（跨窗口 shift_levels，event_refs 血缘） |
| SIGNAL | **PASS** | 8 信号（MULTI_LEVEL_SYNC 6 + WATER_SHIFT_STRONG 2），含 feature_id/阈值依据 |
| STRATEGY | **PASS** | 2 条 AH_MULTI_LEVEL_WATER TRIGGERED（signal_id 引用） |
| DECISION | **PASS** | 2 条 CANDIDATE（strategy_id 引用；direction/selection=UNKNOWN 属允许，规则 13） |

真实血缘链验证：DECISION → STRATEGY → SIGNAL → FEATURE → EVENT → unified_snapshot_id → raw_ref(sha256) → source，全链可追溯（规则 14）。

## 版本追踪（规则 16/51-10）

- pipeline_version 0.1.0、schema_version 2、engine_versions {event:v3, feature:v2, signal:v1, strategy:v1, decision:v1, replay:v2, backtest:v1}、config_version 记录于 pipeline_runs；各层表均有 pipeline_version / engine_version 列

## Replay（规则 23/24/51-12/13/14）

| 项 | 结果 |
|---|---|
| True Replay（独立 replay.db 重建 + 全下游重跑） | **PASS** |
| 无未来泄漏（cutoff 过滤，tests/test_replay.py::test_replay_no_future_leak） | **PASS** |
| 确定性双跑（5 轮真实数据 9330 快照：183/52/86/8/2/2 两次完全一致 + replay_hash 相同） | **PASS** |

## Backtest（规则 25/51-15）

- 基于 Replay：samples(features)=86、events 183、groups 52、signals 8、strategies 2、decisions 2；signal/strategy/decision/event 分布统计；不虚构 ROI

## Failure / 冲突 / 重复 / 非法测试（规则 32/33/34/51-19~22）

| 项 | 结果 |
|---|---|
| Source A DOWN（B 继续） | **PASS** (test_source_down_isolated) |
| Source B DOWN（A 继续） | **PASS** |
| Mapping Conflict（队名同/时间异 → CONFLICT） | **PASS** |
| Mapping Unmapped / Pending / Invalid | **PASS** |
| 重复数据（同 received_at 不重复；异时间保留） | **PASS** |
| 非法数据（odds None/负、非法 line、缺字段、空数据） | **PASS** |

## 测试体系（规则 40/51-16/24）

**59 tests 全部通过**（pytest tests/ -q → 59 passed）：
- Unit: match/market mapping 状态机、line 解析与差分、source adapters、pct 基准、leagues 回归
- Integration: 模块连接、unified 唯一入口
- Pipeline: 完整链路、单轮无事件、乱序输入、Signal→Strategy→Decision 触发
- Replay: 确定性、时间旅行、隔离库、空历史
- Failure: Source 隔离、重复、非法、空数据、枚举完整
- Regression: -0.5→-0.75 识别、空 leagues 回退、SX base 探测

## 全新数据库验收（规则 36/51-17）

- `rm -rf data && python3 -m pipeline.orchestrator` 一步初始化 + 真实采集 + 全链路运行成功（无隐藏脚本/手工建表）

## 性能（规则 42 之后的工程项）

- 批量写入优化（共享连接单事务）：全量双源采集 21s（原逐行 connect/commit >240s 超时）

---

## Final: **PASS**

BB Node V0.1 E2E ACCEPTANCE **PASS** —— 具备宣布 DONE 条件。
