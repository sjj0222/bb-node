# BB-D1 Evidence Matrix - Night Run 2026-10-26

**Branch**: night/bb-node-foundation-20261026  
**Base SHA**: 74cff43929f997f9f72fdbae8649b39221b8b4b8  

## Evidence Classification
- `FACT`: Directly proven by code/raw data
- `SUPPORTED INFERENCE`: Supported by multiple evidence points
- `UNKNOWN`: Insufficient evidence
- `CONFLICT`: Contradictory evidence

## 1. Raw Data Evidence

| Item | Status | Evidence |
|------|--------|----------|
| ladder.txt exists | FACT | 1735 lines, 145839 bytes in repo root |
| ladder_v7.txt exists | FACT | 156 lines, 8188 bytes, contains MARKET_CHANGE blocks |
| 52 option-level transitions extractable | FACT | Verified in audit reports via verify_matrix.py |
| ladder.txt has zero line changes in sequences | FACT | Verified in 04_REAL_DATA_EVIDENCE.md |
| "-0/0.5" appears frequently | FACT | 342 times in ladder.txt, 12 in ladder_v7.txt |
| "0/0.5" (unsigned first leg) appears | FACT | 0 times in both files |
| "-0.5/0", "+0.5/0" appear | FACT | 0 times in both files |

## 2. Code Evidence

| Item | Status | Evidence |
|------|--------|----------|
| events/line.py parse_line bug | FACT | `-0.0 < 0` is False, causes sign loss for "-0/..." splits (line 10-11) |
| events/engine_v3.py pairs by `line` (market-level) | FACT | Line 42: `min(cand, key=lambda x:abs((x["line"] or 0)-(r["line"] or 0)))` |
| events/engine_v3.py compares by `line_raw` | FACT | Line 44-45: `lc = str(a["line_raw"])!=str(r["line_raw"]); info=compare_line(a["line_raw"],r["line_raw"])` |
| sources/bb.py has mk.li (market) vs op.li (option) | FACT | Lines 40,43,46,65 show different sources |
| mapping/market.py has parse_line_quarters | FACT | Exists in origin/phase1, not in main events chain |
| parse_line_quarters is mapping-layer only | FACT | Not used by events/engine_v3.py or replay engines |

## 3. -0.5/0 vs 0/0.5 Equivalence
| Question | Status | Evidence |
|----------|--------|----------|
| Are "-0.5/0" and "0/0.5" equivalent? | UNKNOWN | Neither appears in real data samples. No test coverage for this pair. parse_line_quarters behavior unknown from main. Need explicit business decision. |
| Is "-0/0.5" equivalent to "-0.5/0"? | SUPPORTED INFERENCE | parse_line_quarters treats them same in origin/phase1 tests, phase12 fixed makes them same. But main events/line.py treats differently. |

## 4. Unresolved (U1-U6)
Per 06_AGENT_DISAGREEMENTS.md - all marked UNKNOWN/require decision:
- U1: Cross-detection event type
- U2: "Same line" definition (quarters vs mid)
- U3: Steps unit for cross vs magnitude
- U4: line_raw vs line field sourcing
- U5: canonical_match_id production
- U6: Missing spec document

## Conclusion
BB-D1 issues are real (negative zero parsing bug, data flow mismatch). Fixes exist in isolation (phase12_fixed passes tests) but business semantics for some cases remain unresolved. No changes made to main branch.
