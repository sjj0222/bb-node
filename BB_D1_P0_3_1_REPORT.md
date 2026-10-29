# BB-D1 P0.3.1 报告：canonical_match_id 恢复安全加固

基线分支：audit/bb-d1-canonical-match-id-20261029（提交 2af60e32265e88ee02122e7e60ef4966a3e23b75）
新分支：audit/bb-d1-canonical-match-id-hardening-20261029（独立 worktree）
原工作区：impl/bb-node-tdd-20261026 未修改；main 未修改或合并
保护：features/engine_v2.py、原工作区 events/engine_v3.py 未提交修改及全部未跟踪文件保留；未触碰生产数据库、未执行历史回填

## 1) 映射查询安全性加固

### Schema 与唯一性验证
- `mapping/db.py:init_mapping()` 创建 `match_mappings` 表，包含 `UNIQUE(source, source_match_id)`（第19行）。schema 版本/连接与 DB 由 `database.db.connect()` 使用 `database.db.DB` 控制。
- `get_by_source` 改为使用 `fetchall()` 并**显式检查**：若 0 行返回 `None`，若行数 != 1 返回 `None`（拒绝多条候选）。保留 UNIQUE 约束作为主要唯一性保证，并补充测试验证约束实际生效及多条候选路径的拒绝行为。

### 修改文件
- `mapping/db.py`：`get_by_source` 增加多候选防御（拒绝恢复）。

## 2) canonical ID 一致性校验

### 语义一致性确认
- `mapping/match.py::make_canonical_id(home,away,event_time)` 使用归一化队名和 `int(event_time or 0)//60000` 生成 key。
- `map_match` 在 `status=='matched'` 时用 `(a.home,a.away,a.event_time)` 调用 `make_canonical_id`；`auto_map` 将 `a.home/a.away/a.event_time` 写入 `match_mappings`。字段语义一致。
- 在 `core/collector.py::save_new_layers` 和 `mapping/unified_service.py::unify` 的恢复路径中，**仅在** `home/away/event_time` 全部非空时，重算 `make_canonical_id` 并与映射中的 `canonical_match_id` 比较，一致才恢复。不一致或字段缺失则**拒绝恢复**（不猜测、不伪造）。恢复仍严格要求：唯一来源关联（(source,source_match_id)）、`status=='matched'`、非空 canonical ID。

### 修改文件
- `core/collector.py`：恢复时增加一致性校验
- `mapping/unified_service.py`：恢复时增加一致性校验（并导入 `make_canonical_id`）

## 3) 补齐测试

扩展 `tests/test_canonical_match_sync.py`，临时数据库隔离测试：
1. 唯一且 matched 的映射可以恢复 - PASS
2. 无映射时保持 None - PASS
3. possible/unmatched 映射不能恢复 - PASS（新增）
4. 已传入的非空 canonical ID 不被覆盖 - PASS（新增）
5. source 不同不能串配 - PASS（新增）
6. source_match_id 不同不能串配 - PASS（新增）
7. 唯一约束实际生效（重复插入导致冲突）以及多条候选时拒绝恢复 - PASS（新增）
8. canonical ID 校验逻辑（在证据支持下实现）- 通过一致性校验验证（映射字段完整时校验通过才恢复；字段缺失或不一致则拒绝）

### 测试结果
- `tests.test_canonical_match_sync`: 9/9 OK
- `tests.test_event_pairing` + `tests.test_replay_pairing`（P0.2 回归）: 17/17 OK

## 4) 隔离与验收
- 使用独立 worktree `audit/bb-d1-canonical-match-id-hardening-20261029`，基于 `audit/bb-d1-canonical-match-id-20261029@2af60e3`
- 未修改 main、impl/bb-node-tdd-20261026 或原工作区文件
- 保留 features/engine_v2.py、原工作区 events/engine_v3.py 未提交修改及全部未跟踪文件
- 未接触生产数据库，未执行历史回填
- 本地与远程分支 HEAD 一致
- 提交并推送新分支，不创建 PR、不合并、不改动 main
- 生产数据库被触碰：**否**

## 差异文件
- `mapping/db.py`（修改）
- `core/collector.py`（修改）
- `mapping/unified_service.py`（修改）
- `tests/test_canonical_match_sync.py`（修改）

## 结论
P0.3.1 **满足进入合并评审的条件**。安全缺口已加固（显式多候选拒绝、基于证据的一致性校验、不覆盖已有非空 ID、不恢复非 matched、严格按 (source,source_match_id) 隔离），针对性测试齐全且全部通过，无 P0.2 回归。
