# Test Baseline - Night Run 2026-10-26

**Branch**: night/bb-node-foundation-20261026  
**Base SHA**: 74cff43929f997f9f72fdbae8649b39221b8b4b8  

## Tests Run

| Test Suite | Path | Tests | Result | Exit |
|------------|------|-------|--------|------|
| bb_node_overnight_v1 | `bb_node_overnight_v1/tests/` | 12 | OK | 0 |
| bb_main_unit_tests_v1 | `bb_main_unit_tests_v1/tests/` | 10 | OK | 0 |
| phase12_fixed (on branch) | `audit/bb_d1/phase12_fixed/tests/` | 11 | OK | 0 (verified earlier) |

**Total passing (sampled)**: 33 tests  
**Failures**: 0 in tested suites  
**Skipped**: 0

## Notes
- Main repo root has no tests/ directory
- pytest not installed, using unittest
- Some test dirs are in untracked/historical locations
