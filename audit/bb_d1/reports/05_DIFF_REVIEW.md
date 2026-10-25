# 05_DIFF_REVIEW.md — 变更文件与 diff 摘要

## 变更文件

1. `events/line.py`（修改，+148/-59）
2. `tests/__init__.py`（新建，空）
3. `tests/test_line_phase12.py`（新建，9 个测试）

## diff 摘要

### parse_line 修复
- 添加 `math.isfinite()` 检查（但 `inf`/`nan` 仍未被拒绝，需后续修复）
- 添加符号提取逻辑（先剥符号，再作用于所有腿）
- 添加非法输入检查（重复分隔符、重复符号、缺失腿）
- 添加 `sorted()` 排序（与 parse_line_quarters 一致）

### compare_line 修复
- 添加 `_mid_from_legs()` 函数（基于 quarters 的 mid 计算）
- 添加 legs 相同 → SAME 判定
- 添加 mid 相同 → SAME 判定
- 添加跨盘检测（mid 异号且非 0 → CROSS/SIGN_FLIP）
- 保留现有 DEEPER/SHALLOWER/QUARTER/HALF/MULTI_STEP 逻辑

## 兼容性
- 保留现有 `changed`、`direction`、`change_type`、`steps` 字段
- 不新增 `CROSS` 或 `SIGN_FLIP`（避免契约冲突）
- 跨盘时仍输出 `DEEPER`/`SHALLOWER`（按 `|Δdepth|`）
- `steps` 统一为 `|Δdepth|/0.25`（四分之一球单位）

## 风险
- `inf`/`nan` 仍未被拒绝
- 银行家舍入问题继承自 `parse_line_quarters`
- 混合符号腿（`-1/+1`）仍可能产生 `steps=0.0`
EOF
