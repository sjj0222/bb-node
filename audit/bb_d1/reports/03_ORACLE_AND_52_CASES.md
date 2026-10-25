# 03_ORACLE_AND_52_CASES.md — 52 条真实盘口迁移 oracle

## Oracle 来源

52 条迁移来自 `ladder_v7.txt` 的 26 个 MARKET_CHANGE 块，每块按选项配对出 2 条（消失档位 option → 出现档位 option）。

Oracle 预期基于 `origin/phase1:mapping/market.py::parse_line_quarters` 的 quarters/mid 编码：
- quarters 相同 → SAME
- mid 异号且非 0 → 跨盘（FLIP）
- 否则 → 幅度变化（MAGNITUDE）

## 验证结果

| 指标 | 数值 |
|---|---|
| 52 条迁移 | **全部 PASS** (exit code 0) |
| 通过 | 52 |
| 失败 | 0 |
| 未知 | 0 |

## 52 条迁移的分类分布

| 规范分类 | 条数 |
|---|---|
| MAGNITUDE（幅度变化） | 24 |
| FLIP（跨盘） | 28 |
| SAME（同一盘口） | 0 |

## 测试覆盖

- `test_52_migrations`：52 条迁移全部通过
- `test_neg_zero_splits`：`-0/0.5` ≡ `-0.5/0`（SAME）
- `test_neg_zero_vs_pos_split`：`-0/0.5` vs `+0/0.5`（changed=True）
- `test_pos_zero_equiv`：`+0/0.5` ≡ `0/0.5`（SAME）
- `test_invalid_inputs`：非法输入返回 UNKNOWN
- `test_existing_regression_cases`：11 个原始回归用例全部通过
- `test_whitespace_handling`：空白处理
- `test_neg_zero_not_silent`：`-0/0.5` 的 legs 正确保留符号
- `test_norm_basic`：norm 基本功能

## 未决问题

- `inf`/`nan` 未被拒绝（需要后续修复）
- 银行家舍入问题继承自 `parse_line_quarters`（需要加固）
- 跨盘分类仍用 DEEPER/SHALLOWER（未引入 CROSS/SIGN_FLIP）
EOF
