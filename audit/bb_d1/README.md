# BB-D1 Recovery Audit Branch

This branch contains audit evidence and candidate fixes for the BB-D1 issue in bb-node.

**Branch**: audit/bb-d1-recovery-20261025  
**Base**: 74cff43929f997f9f72fdbae8649b39221b8b4b8 (main)  
**Created**: 2025-10-25  
**Status**: Recovery/Audit - NOT ACCEPTED FOR MERGE TO MAIN

## Contents

- `reports/` - Full audit reports (01_CANONICAL_LINE_SPEC.md through 07_RUN_LOG.md), agent disagreements, fix plans, verification scripts and outputs
- `candidate/` - BB-D1 candidate fixes from devcopy/ (events/line.py, tests) - ISOLATED, not merged
- `phase12_fixed/` - Verified fixed version from phase12_work/ (passes 11 tests) - ISOLATED, not merged
- `data/` - Raw data samples (ladder.txt, ladder_v7.txt) used in analysis
- `logs/` - Context files (original events/line.py, events/engine_v3.py)

## Important Notes

- This is an AUDIT/RECOVERY branch only. No changes have been merged to main.
- All fixes are in isolated directories for review only.
- 6 business definition items remain UNRESOLVED (U1-U6) per 06_AGENT_DISAGREEMENTS.md
- The devcopy candidate has known issues (23% error rate on real data) - see reports
- phase12_fixed version addresses core issues but requires further review

## Key Issues (Unresolved)

See reports/06_AGENT_DISAGREEMENTS.md for full details:
- U1: Cross-detection event type
- U2: "Same line" definition (quarters vs mid)
- U3: Steps unit for cross vs magnitude changes
- U4: line_raw vs line field sourcing
- U5: canonical_match_id production
- U6: Missing spec document

