# BB-D1 P0.2 报告：无效市场 ID 防护、Replay 配对修复与 canonical_match_id 调查

基线提交：bb28da42f89f223e65a00a9f8bc392cbe8b38cda（audit/bb-d1-event-pairing-20261027 / audit/bb-d1-replay-pairing-20261028）
原工作分支：impl/bb-node-tdd-20261026（未修改）
main：未修改或合并
工作区：audit/bb-d1-replay-pairing-20261028（独立 worktree）

## 一、无效 ID 防护（Task A）- events/engine_v3.py

### 处理策略（证据）
- 定义 `_is_valid_market_id(v)`：None、空字符串、纯空白、字符串 `"None"`（大小写不敏感处理）均视为无效。
- 在配对前检查 `source_market_id`：若缺失字段（KeyError）、或无效，跳过该记录，不参与配对（不放入配对桶，不参与候选匹配）。
- 即使两侧均为相同无效值（如均为空字符串或均为 `"None"`），也不会因无效值相同而配对。
- 仅跳过无效记录，不修改原始数据；最小改动，不影响正常有效 ID 的配对逻辑。
- keys 仍包含 `source_market_id`（沿用 P0.1 修复）以区分不同市场实例。

修改文件：`events/engine_v3.py`

### 测试变更
- 修正 `tests/test_event_pairing.py::test_empty_source_market_id_pairs_with_empty`：预期由"空字符串之间应正常配对并产生事件"改为"无效ID不参与配对，预期 0 个事件"。
- 新增 `tests/test_event_pairing.py::test_string_none_source_market_id_not_paired`（字符串 `"None"` 不配对）
- 新增 `tests/test_event_pairing.py::test_missing_source_market_id_not_paired`（缺失 `source_market_id` 字段时视为无效，不配对）

定向测试结果（临时 DB，隔离数据）：
```
Ran 7 tests in 0.101s
OK
```

## 二、Replay 引擎修复（Task B）

### 调查结论
`replay/event_v1.py` 和 `replay/event_v2.py` 的配对逻辑与修复前的 `events/engine_v3.py` 相同：使用 `(source, canonical_match_id, market_type, period, side, option)` 作为配对键，未包含 `source_market_id`，且未对无效 ID 做防护。证据显示存在同类跨市场实例错配风险，且 `unified_snapshots` 中存在 `source_market_id`。因此按要求加入 `source_market_id` 到配对键并增加无效 ID 防护。

### 修改文件
- `replay/event_v1.py`：增加 `_is_valid_market_id`，配对键扩展为包含 `source_market_id`，跳过缺失/无效的 `source_market_id`
- `replay/event_v2.py`：增加 `_is_valid_market_id`，配对键扩展为包含 `source_market_id`，跳过缺失/无效的 `source_market_id`

### 针对性测试（tests/test_replay_pairing.py）
覆盖：相同有效市场 ID 能正确配对；不同市场 ID 不会配对；无效市场 ID 不会触发配对；不同比赛不会交叉配对；无匹配候选时不会生成错误事件。全部通过。

定向测试结果：
```
Ran 10 tests in 0.093s
OK
```
使用临时数据库和隔离测试数据，未调用生产 main()。

## 三、canonical_match_id 生产链路调查（Task C，只读）

1. **生成环节**：`mapping/match.py::make_canonical_id()` 基于归一化 home/away 和 `event_time//60000` 生成；仅在 `map_match()` 判定 `status == "matched"` 时生成，否则为 `None`。生产中主要由 `core/collector.py::save_new_layers()` 调用 `auto_map(x,x)`（自映射）获取 cid，再传给 `unify(r,cid)` 写入 `unified_snapshots`。
2. **是否一直写入 None？** 存在路径写入 None：若自映射未达 `matched`（如 `event_time` 缺失导致 `time_score==0.0`，自匹配可能落入 `possible` 而非 `matched`）、或 `auto_map` 返回 None、或直接调用 `unify/save_unified` 传入 None 等情况。
3. **match_mappings 写入但未回填 unified_snapshots？** `mapping/service.auto_map()` 只调用 `save_mapping()` 写入 `match_mappings`，仓库中无代码将 `match_mappings` 的 `canonical_match_id` 回填到 `unified_snapshots`。`unified_snapshots.canonical_match_id` 仅在写入时由调用方传入，故存在映射已记录但快照未更新的情况。
4. **能证明 vs 需更多证据**：能证明的有源头/匹配逻辑/collector 传递/事件引擎过滤等代码证据；需更多证据的有实际库中 NULL 比例、match_mappings 与 unified_snapshots 不一致的实例、其他写入路径的实际使用等。
5. **对事件引擎影响**：事件引擎（events/engine_v3、replay/event_v1、replay/event_v2）均只处理 `canonical_match_id is not null` 的记录。若大量记录为 None，会导致记录无法进入配对流程（漏报）；若映射不一致也会造成处理范围不一致。

本子任务仅调查，不修改 match mapping 生产逻辑。

## 四、工作区保护
- 原工作区 `impl/bb-node-tdd-20261026` 未修改；`features/engine_v2.py` 未提交修改及全部未跟踪文件保留
- 未修改或合并 `main`

## 五、修改文件清单
- `events/engine_v3.py`（修改）
- `replay/event_v1.py`（修改）
- `replay/event_v2.py`（修改）
- `tests/test_event_pairing.py`（修改）
- `tests/test_replay_pairing.py`（新增）

## 六、验证
- 仅运行与本次改动直接相关的定向测试，使用临时 DB/隔离数据
- 测试失败先调查原因，未放宽断言掩盖问题
- 未宣称未运行测试通过

## 七、建议
**建议创建 PR**。修复最小且有测试覆盖，解决无效 ID 配对风险并补齐 replay 引擎同类问题。canonical_match_id 调查发现了可能导致事件引擎过滤记录的风险点，建议后续跟进。
