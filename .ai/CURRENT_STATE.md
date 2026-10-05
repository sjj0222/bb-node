# BB Node — Current State

## 1. Project Identity

- Project: BB Node
- Memory system: AI Project Memory V0.1
- Current Git branch: ai-memory-v0.1
- Branch created from: phone-sync
- Base commit: 14c38d3
- Remote V0.2 branch: origin/v0.2

## 2. Important Branches

### main
Stable/main development line.

### phone-sync
Current phone-sync development line.
Latest confirmed commit before creating ai-memory-v0.1:
- 14c38d3 — unify replay event calculation

### origin/v0.2
Independent V0.2 development line.
Important commits:
- cd0b7ce — BB Node V0.1 real E2E PASS
- 03ae973 — add V0.1 acceptance report
- 18c289d — V0.2 major feature implementation, 108 tests PASS
- d339ab3 — V0.2 P2P/Source Health/Monitor recovery additions, 115 tests PASS
- 35ea228 — V0.2 acceptance document

## 3. V0.2 Acceptance Baseline

V0.2 is recorded as PASS.

Confirmed:
- V0.1 baseline: PASS
- 115 total tests PASS
- Real dual-source E2E: PASS
- Monitor: PASS
- Market Extension: PASS
- Data Quality: PASS
- P2P: PASS
- Strategy/Decision Plugin: PASS
- Replay V2: PASS
- Backtest V2: PASS
- Real E2E pipeline: PASS

## 4. V0.2 Stability Status

24h stability:
- Running
- Started: 2026-10-04
- Current task is not yet confirmed complete in this memory snapshot
- Final determination must use the stability_runs table if the environment terminates before completion

72h stability:
- Not completed
- This is a target, not a V0.2 FAIL condition

## 5. V0.2 Environment

Acceptance baseline environment:
- Python: 3.12.11
- Database: SQLite
- Main DB: data/bb.db
- Replay DB: data/replay.db
- Schema migration: V2 -> V3 idempotency verified
- Main DB uses WAL

## 6. Real Sources

Source A:
- BB API
- Status: PASS
- source_health: UP
- 3012 records in acceptance test

Source B:
- SX Bet
- Status: PASS
- source_health: UP
- 68 records in acceptance test

Source isolation:
- A failure does not block B
- HTTP success, DATA success and PIPELINE success are treated separately

## 7. Key V0.2 Results

Monitor:
- State machine PASS
- Manual mode PASS
- Daemon/background mode PASS
- Watchlist PASS
- Alert system PASS
- Source failure isolation PASS

Market:
- AH / OU / 1X2 mapped
- corner_over_under real mapping PASS
- Unsupported markets are explicit UNSUPPORTED/PENDING
- No silent dropping

Data Quality:
- Score: 100.0
- total: 21667
- valid: 21667
- invalid: 0
- duplicate: 0
- conflict: 0
- unmapped: 0
- one out_of_order record explicitly marked

P2P:
- RAW + Unified synchronized
- Derived results are not synchronized
- RAW cross-node hash verification PASS
- Dedup PASS
- Integrity rejection PASS
- Conflict preservation PASS
- Protocol incompatibility rejection PASS
- Recovery/incremental sync PASS

Replay:
- No Future Leakage PASS
- Fixed-window double-run equivalence PASS
- 18,519 snapshots
- 762 events
- 242 features
- 41 signals
- 10 strategies
- 10 decisions

Backtest:
- Based on Replay
- samples=249
- triggered=10
- decisions=10
- No fabricated ROI when result fields are absent

## 8. Known Important Distinction

V0.2 acceptance is PASS.

This does NOT mean every future stability target is complete.

In particular:
- 24h stability completion must still be verified when required
- 72h is a target and is not itself a V0.2 FAIL condition

## 9. Memory Rules

This file is a project-state snapshot, not a chat transcript.

Do not infer missing project facts from memory.

When a new decision materially changes architecture, requirements, acceptance criteria, branch strategy or project status:
1. Record the decision in DECISIONS.md
2. Update CURRENT_STATE.md if the current state changes
3. Update TODO.md if the next action changes

If two sources conflict:
- Do not silently overwrite the existing state
- Record the conflict
- Identify the source and commit
- Ask for resolution when necessary
