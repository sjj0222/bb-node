# BB-D1 P0.3 报告：canonical_match_id 生产链路修复

基线分支：audit/bb-d1-replay-pairing-20261028（提交 15059435f7728ea4c09e518d2b926232be648e01）
新分支：audit/bb-d1-canonical-match-id-20261029（独立 worktree）
原工作区：impl/bb-node-tdd-20261026 未修改；main 未修改或合并
保护：features/engine_v2.py 未提交修改及全部未跟踪文件保留；未触碰生产数据库、未执行迁移、未修改 RAW

## 一、映射语义（Task A）

### 1) mapping/match.py
- `norm_name`：归一化队名（小写、NFKC、去空格/连字符/下划线/点/引号、去除非字母数字中文以外字符）
- `name_score`：归一化后完全相等得 1.0，否则用 SequenceMatcher 比例
- `time_score(a,b,tolerance=900s)`：若任一为 None 或差值>tolerance 返回 0.0，否则 `max(0,1 - diff/tol)`；**event_time 缺失会导致 time_score 0.0**
- `make_canonical_id(home,away,event_time)`：键为 `norm_name(home)|norm_name(away)|int(event_time or 0)//60000`，返回 `cm_` + sha256[:20]。**仅在有足够信息生成键时才应调用；不能为 event_time=None 伪造有意义的键**
- `match_score(a,b)`：`hs*0.4 + aws*0.4 + ts*0.2`。若 `hs==1 and aws==1 and ts>=0.8` -> `matched`；elif `score>=0.88` -> `matched`；elif `score>=0.72` -> `possible`；else `unmatched`。**只有 status==matched 才会在 map_match 中生成 canonical_id**
- `map_match(a,b)`：计算 score，若 matched 则用 `make_canonical_id(a.home,a.away,a.event_time)` 生成 cid，否则 cid=None，返回带 `canonical_match_id/status/confidence/...` 的 dict

### 2) core/collector.py::save_new_layers
- 归一化（BBAdapter.normalize）得到 records，取首条 `x` 调用 `auto_map(x,x)` 获取 `mm["canonical_match_id"]`，再对所有 records 调用 `unify(r,cid)` 写入 unified_snapshots。自映射若未达 matched 则 cid 可能为 None。

### 3) mapping/service.py::auto_map、mapping/db.py::save_mapping
- `auto_map(a,b)`：`r = map_match(a,b)` → 组装数据（含 `canonical_match_id = r["canonical_match_id"]`，status/confidence 等）→ `save_mapping(data)` → 返回 data。**只写入 match_mappings，不更新 unified_snapshots**
- `save_mapping`：INSERT INTO match_mappings (...,canonical_match_id,...) ON CONFLICT(source,source_match_id) DO UPDATE ...（UNIQUE(source, source_match_id)）。可写入 canonical_match_id=None（unmatched）。

### 4) mapping/unified_service.py::unify、mapping/unified_db.py::save_unified
- `unify(record, canonical_match_id=None)`：先 `normalize(record)` 获取 market，再调用 `save_unified(...)` 传入 `canonical_match_id`。写入约束主要由 schema（unified_snapshots.canonical_match_id 可为 NULL）决定。
- `save_unified`：INSERT OR IGNORE 到 unified_snapshots，直接使用传入的 `canonical_match_id` 写入。

### 5) match_mappings 关联方式
- Schema：`UNIQUE(source, source_match_id)`，字段含 `canonical_match_id TEXT`、`status`、`confidence` 等。可通过 `(source, source_match_id)` **可靠且唯一**地查回映射记录。若记录存在且 `status=='matched'` 且 `canonical_match_id` 非空，则可视为可靠映射。若关联不唯一（实际受 UNIQUE 约束限制）或无记录，或 status 非 matched，则**不能**推断/猜测 canonical ID。

## 二、修复（Task B）

### 设计原则
- 不改变业务匹配阈值、不把 "possible" 升级为 "matched"、不伪造比赛 ID
- event_time=None 时不强行生成 ID
- 仅使用**明确的源标识**（source + source_match_id）查回已有可靠映射
- 只处理"已存在且可靠"的映射，不臆测；无法安全修复的路径如实报告
- 不做历史批量回填（仅面向新写入的路径）

### 实施的安全局部修复
1. **core/collector.py::save_new_layers**
- 在获取 `cid = mm.get("canonical_match_id")` 后，若为空，尝试 `get_by_source(x.source, x.source_match_id)`。仅当存在映射且 `status == 'matched'` 且 `canonical_match_id` 非空时才采用。
- 导入 `get_by_source`。

2. **mapping/unified_service.py::unify**
- 新增从 `match_mappings` 按 `(record.source, record.source_match_id)` 查找的兜底逻辑：若传入 `canonical_match_id` 为空，仅在找到 `status=='matched'` 且 `canonical_match_id` 非空的可靠映射时才使用。导入 `get_by_source`。

这确保：新写入的 unified_snapshots 在符合条件时能复用已存在的可靠映射，避免因自映射未达 matched（如 event_time 缺失导致落入 possible）而漏同步。不会改变匹配语义，也不会为缺乏证据的情况生成 ID。

## 三、测试（Task C）

新增测试：`tests/test_canonical_match_sync.py`（临时数据库，隔离数据）
1. `test_unify_uses_existing_matched_mapping_by_source` - 已存在 matched 映射时，unify 无传入 cid 也能从 match_mappings 恢复并写入正确 canonical_id（PASS）
2. `test_unify_does_not_fabricate_when_no_mapping` - 无映射时不伪造 ID，unified_snapshots.canonical_match_id 保持 NULL（PASS）
3. `test_self_match_without_event_time_does_not_fabricate` - event_time=None 时自映射不达 matched 且不伪造 ID（PASS）

回归测试（P0.2）：
```
Ran 17 tests in 0.116s
OK
```
（tests.test_event_pairing + tests.test_replay_pairing 全部通过，无回归）

所有测试均使用临时 DB，不调用生产 main()，不触碰生产数据。

## 四、交付清单（Task D）

### 修改文件
- `core/collector.py`（修改）：新增对已有 matched 映射的兜底恢复
- `mapping/unified_service.py`（修改）：unify 增加按源标识恢复可靠映射的兜底逻辑
- `tests/test_canonical_match_sync.py`（新增）：canonical_match_id 同步测试

### 设计依据
- match_mappings 以 `(source, source_match_id)` 唯一标识源比赛，可可靠查回
- 仅在 `status=='matched'` 且 `canonical_match_id` 非空时才使用，避免猜测/升格 possible
- 不修改匹配阈值，不为 event_time 缺失等情况伪造 ID
- 仅影响新写入路径，不做历史批量回填

### 测试结果
- `tests.test_canonical_match_sync`: 3/3 OK
- `tests.test_event_pairing` + `tests.test_replay_pairing`: 17/17 OK（无回归）

### 仍未解决的限制
- **历史数据未回填**：本次未对生产/已有 unified_snapshots 执行历史批量回填。若历史行已写入 canonical_match_id=NULL 且后续才有匹配映射，将仍需单独的受控回填流程。
- **数据模型约束**：若映射缺失或不可靠（未达 matched/无记录），无法安全生成 canonical_id。对于 event_time 缺失导致自映射落入 possible 的情况，在现有匹配语义下不应强行提升。
- **非 collector 路径**：虽然在 unify 增加了兜底，但若上游完全未经过这些路径且无匹配映射，仍可能产生 NULL（这是现有模型下的合理保守行为）。

### 提交与推送
- 已提交到分支 `audit/bb-d1-canonical-match-id-20261029`
- 已推送到远程
- 未创建/合并 PR，未修改 main
- **生产库未被触碰**（全部使用临时数据库，未执行生产数据库迁移、未删除或重写原始 RAW 数据）
- 新分支本地与远程 SHA 一致，原工作区 impl/bb-node-tdd-20261026 未改动，features/engine_v2.py 未提交修改及所有未跟踪文件均保留
