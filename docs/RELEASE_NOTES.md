# bb-node 发布说明 (Release Notes)

## 0.3.0-rc1 (Phase 1-13, 发布候选)

基于 v0.2 基线(35ea228)按规格 BBN-PRD-ARCH-SPEC V1.0 完成 Phase 1-13。
分支 phase1, 提交链: e64f5b8(P1) -> 087d3c5(P2) -> 0d94c23(P3) ->
f4d947b(P4) -> 4e98dbc(P5) -> 59d670e(P6) -> a200e38(P7) -> 16fbf82(P8-10)
-> eb71556(P11) -> 71b5dcc(P12) -> (P13 本提交)。

### Schema 演进
database.schema_version: v0.2 基线 3 -> 4(P2 RAW/幂等) -> 5(P4 质量拒绝表)
-> 6(P5 映射审计) -> 7(P6 盘口/主盘口) -> 8(P7 Unified) -> 9(P8-10
事件/特征/信号/回放) -> 10(P11 备份记录) -> 11(P12 稳定性原因码)。
迁移链 2->3->...->11 幂等; 每步只增列/建表/建视图, 不删改既有数据。

### 风险修复(R 清单)
- R1 负向四分位盘口符号反转: 修复(Phase 6, parse_line_quarters 显式保留
  符号), 只对新数据生效。
- R2 bb 分页失败静默 success=1: 修复(Phase 2, partial/error_code 落库)。
- R3 映射变更无审计: 修复(Phase 5, mapping_audit/审批队列/下游失效标记)。
- R4 未映射只计数不落库: 修复(Phase 2, unmapped_records 落库)。
- R5 无单实例锁: 修复(Phase 1, core/lock.py, PID+cmdline 防复用)。
- R8 稳定性恒 PASS: 修复(Phase 12, 显式门限+原因码)。

### 测试规模
全量 pytest: 115(v0.2 基线) -> 129(P1) -> 141(P2) -> 160(P3) -> 174(P4)
-> 182(P5) -> 196(P6) -> 206(P7) -> 223(P8-10) -> 233(P11) -> 242(P12+13)。

### 新增 CLI
init/check/doctor(+--json/退出码 0/1/2)、mapping(list/approve/reject/
defer/revoke/audit)、unified(query/latest/series/compare/plan)、
backup(create/list/restore)、security(scan/rotate)、monitor(start/stop/
status/restart/once)、source status、quality run。

### 待确认清单(由用户拍板, 不阻塞发布)
1. 推送凭据: origin 为明文 https 无写权限, 需用户提供写权限 PAT 或自行
   push(本报告附一键推送脚本)。
2. 主盘口默认策略 main-v1 已按规格默认实现, 如需调整优先级/冲突策略
   需确认。
3. 映射人工审批门槛(队列自动入队范围)待用户确认阈值。
4. Phase 14(Windows/Android UI 与同步)按规格可延期。

### 已知限制
见 docs/OPERATIONS.md §8。
