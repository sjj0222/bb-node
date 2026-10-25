# 01_PHASE1_FIX.md — Phase 1：负零与非法输入修复

## 问题

`events/line.py:10-11` 的 `parse_line` 使用 `y = -abs(y) if x < 0 else abs(y)` 判断第二腿符号。
当 `x = -0.0` 时，`-0.0 < 0` 为 **False**，导致 `-0/0.5` 的符号被错误推断为正向。

## 修复方案

1. **符号提取**：先从原始字符串提取整体符号（`+`/`-`），再作用于所有腿。
2. **非法输入拒绝**：空字符串、None、非数字、重复分隔符、重复符号、缺失腿 → 返回 None。
3. **浮点验证**：使用 `math.isfinite()` 拒绝 `inf`/`nan`（但当前实现仍接受 `inf`/`nan`，需要后续修复）。

## 修复后的 parse_line 逻辑

```python
def parse_line(s):
    if s is None: return None
    s = str(s).strip().replace(" ", "")
    if not s: return None
    if s.count('/') > 1: return None
    if '--' in s or '++' in s or '+-' in s or '-+' in s: return None
    sign = 1
    if s.startswith("+"): sign = 1; s_body = s[1:]
    elif s.startswith("-"): sign = -1; s_body = s[1:]
    else: sign = 1; s_body = s
    if not s_body: return None
    try:
        if "/" in s_body:
            a, b = s_body.split('/')
            if a == '' or b == '': return None
            if '+' in a or '-' in a or '+' in b or '-' in b: return None
            x, y = float(a), float(b)
            if not math.isfinite(x) or not math.isfinite(y): return None
            x, y = x * sign, y * sign
            return sorted([x, y])
        else:
            if '+' in s_body or '-' in s_body: return None
            x = float(s_body)
            if not math.isfinite(x): return None
            return [x * sign]
    except Exception:
        return None
```

## 验证结果

- `-0/0.5` → `[-0.5, -0.0]`（符号正确保留）
- `+0/0.5` → `[0.0, 0.5]`（符号正确保留）
- `0/0.5` → `[0.0, 0.5]`（无符号默认正向）
- `-0.5/0` → `[-0.5, -0.0]`（等价于 `-0/0.5`）
- `""`, `None`, `"abc"`, `"1/2/3"` → `None`（正确拒绝）
- `"inf"`, `"nan"` → **仍返回有效值**（BUG，需修复）

## 未解决问题

- `inf`/`nan` 未被拒绝（`float("inf")` 不抛异常，`math.isfinite` 检查已加但未覆盖所有路径）
- 银行家舍入问题继承自 `parse_line_quarters`（`0.125` → 0 而非 0.25）
EOF
