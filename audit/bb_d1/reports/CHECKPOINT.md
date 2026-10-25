# CHECKPOINT.md — Phase 1+2 完成状态

## 完成状态

| 阶段 | 状态 | 关键产出 |
|---|---|---|
| 隔离副本创建 | DONE | `phase12_work/`（独立 git，baseline commit 0ea21ae） |
| Phase 1：负零与非法输入 | PARTIAL | 负零已修复；inf/nan 未拒绝 |
| Phase 2：规范化统一与比较 | DONE | 52/52 oracle 通过；等价性正确 |
| 测试与验证 | DONE | 9 测试，全部 PASS，exit code 0 |
| 报告交付 | DONE | 7 份报告 + CHECKPOINT |

## 未解决问题

1. `inf`/`nan` 未被拒绝（`float("inf")` 不抛异常，`math.isfinite` 检查已加但未覆盖所有路径）
2. 银行家舍入问题继承自 `parse_line_quarters`（`0.125` → 0 而非 0.25）
3. 混合符号腿（`-1/+1`）仍可能产生 `steps=0.0`

## 续跑指令

1. 读取 `00_SUMMARY.md` → `01_PHASE1_FIX.md` → `02_NORMALIZATION.md`
2. 修复 `inf`/`nan` 拒绝（在 `parse_line` 的 `float()` 调用后加 `math.isfinite` 检查）
3. 修复银行家舍入（使用 `math.floor(x*4 + 0.5)` 或 `decimal` 模块）
4. 运行完整测试集验证
5. 不得提交、推送、合并或修改正式仓库

## 安全检查

- 正式项目未被修改：`git status` 仅 `?? devcopy/`
- 所有修改都在 `phase12_work/`（仓库外隔离副本）
- 无 `__pycache__`、`.pyc`、`.db`、`.log` 文件产生
- 未执行任何写操作到正式项目
EOF
echo "done"
