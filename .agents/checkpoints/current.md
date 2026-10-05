---
title: bb-node-ai-memory-integration
created_at: 2026-10-05 18:50:07 +0800
expires_at: never
checkpoint_schema: agent-handoff/v1
checkpoint_scope: repo
checkpoint_dir: .agents/checkpoints
created_by: codex
compatible_agents: codex, claude-code, opencode, generic
branch: ai-memory-v0.1
base_commit: d0dccc2dea8a00beebb58e118561197edd9f0f55
checkpoint_kind: current
git_state: dirty
---

# bb-node-ai-memory-integration

## Agent Handoff
- Created by: codex
- Checkpoint protocol: `agent-handoff/v1`
- Shared checkpoint directory: `.agents/checkpoints/`
- Compatible agents: Codex/OpenAI CLI, Claude Code, opencode, and generic programming agents.
- Resume rule: trust this file over hidden chat memory; verify git state before editing.
- Long-term project facts belong in `.ai/`; this checkpoint records the current implementation/handoff state.
- Do not silently overwrite conflicting project facts. Record corrections in `.ai/DECISIONS.md` or `.ai/CURRENT_STATE.md`.

## Session Goal
- Establish a durable cross-agent handoff layer for bb-node.
- Integrate repo-local `.agents/checkpoints/` with the existing `.ai/` project-memory layer.
- Produce a strict-valid `current.md` that can be read by Codex, Claude Code, opencode, or another compatible agent.
- Do not modify existing bb-node code or unrelated local files during this integration.

## Current State
- Repository: `sjj0222/bb-node`.
- Current branch: `ai-memory-v0.1`.
- `ai-memory-v0.1` is based on `phone-sync` and adds the `.ai/` AI project-memory baseline.
- `origin/v0.2` is an independent V0.2 development line and must not be silently merged into this branch.
- `.ai/` already contains:
  - `CURRENT_STATE.md`
  - `REQUIREMENTS.md`
  - `DECISIONS.md`
  - persistent task list file
  - `CHANGELOG.md`
  - `REJECTED.md`
- `.ai/CURRENT_STATE.md` is the current long-term project-state reference.
- V0.2 acceptance baseline previously recorded as PASS:
  - V0.1 baseline
  - 115 tests
  - real dual-source E2E
  - monitor
  - market extension
  - data quality
  - P2P
  - strategy/decision plugin
  - replay V2
  - backtest V2
  - real E2E pipeline
- Data-quality baseline recorded as 100.0: total/valid 21667, invalid/duplicate/conflict/unmapped 0.
- Source A BB API and Source B SX Bet are recorded as PASS.
- 24-hour stability test started 2026-10-04 and is still in progress unless a later verification explicitly proves completion.
- 72-hour stability has not been completed; it is a target, not a V0.2 failure condition.
- The current checkpoint is for the AI-memory/handoff integration and does not redefine V0.2 acceptance.

## Key Chat Context
- User requires project continuity across ChatGPT, Codex, opencode, and other coding agents.
- The project must have a single durable source-of-truth architecture rather than multiple competing memory systems.
- `.ai/` is the long-lived project-memory layer for requirements, decisions, state, task list, changelog, and rejected paths.
- `.agents/checkpoints/` is the session/phase handoff layer for current work and resume information.
- Git/GitHub is the durable synchronization layer for code and tracked project-state files.
- Checkpoint files must not be treated as automatic ChatGPT conversation memory.
- Hidden model reasoning is not persisted; only explicit project facts, decisions, constraints, verification results, and handoff information should be recorded.
- Explicit do-not-do:
  - Do not use `git add .` in the current repository state.
  - Do not delete, rename, modify, or overwrite the existing untracked `.bak` and `export_today*` files.
  - Do not change `.ai/` contents merely to make the checkpoint pass validation.
  - Do not merge or rewrite the independent `v0.2` branch as part of this integration.
  - Do not claim 24h or 72h stability completion without fresh verification.
- Rejected/paused paths relevant to continuity:
  - `agentmemory` was tested on Termux but its full worker depends on an unavailable Android/arm64 `iii-engine`; it is not the current persistence layer.
  - `total-recall` 4.2.3 reports unsupported `android/arm64`; it is not the current persistence layer.
  - The repo-local `agent-checkpoint` protocol is retained because it is plain Markdown, Git-friendly, cross-agent, and works on Termux.
- The exact architectural rule to preserve is: `.ai` = long-term truth; `.agents/checkpoints` = current handoff; Git/GitHub = durable transport and versioning.

## Files In Play
- `.ai/CURRENT_STATE.md` — long-term current project state.
- `.ai/REQUIREMENTS.md` — long-term requirements.
- `.ai/DECISIONS.md` — architectural and implementation decisions.
- `.ai/` persistent task list — long-term unfinished work and follow-up items.
- `.ai/CHANGELOG.md` — persistent project change history.
- `.ai/REJECTED.md` — rejected/abandoned approaches.
- `.agents/checkpoints/current.md` — current cross-agent handoff.
- `~/.agents/skills/repo-checkpoint/` — installed checkpoint skill, version 0.4.0.
- `~/.agents/skills/repo-resume/` — installed resume skill.
- `data/bb.db` and `data/replay.db` are project runtime databases and are ignored by Git.
- Existing local untracked files that must remain untouched:
  - `core/collector.py.bak`
  - `events/engine_v3.py.bak`
  - `events/engine_v3.py.bak2`
  - `events/engine_v3.py.bak3`
  - `export_today.py`
  - `export_today.py.bak`

## Verification
- `repo-checkpoint` version 0.4.0 has been installed globally under `~/.agents/skills/`.
- `repo-checkpoint/scripts/save_checkpoint.py --help` works on Termux.
- `repo-resume/scripts/resume_snapshot.py --help` works on Termux.
- A repo-local checkpoint scaffold was successfully created for this repository.
- The checkpoint protocol has been tested independently in `~/agent-checkpoint-test`.
- Independent checkpoint tests confirmed:
  - checkpoint creation works;
  - `resume_snapshot.py` can read checkpoints;
  - `list` works;
  - strict validation rejects unresolved placeholders.
- Current bb-node Git state was inspected before integration.
- Current branch is `ai-memory-v0.1`.
- The current Git working tree is dirty only because of the six pre-existing untracked local files listed above plus the newly created `.agents/checkpoints/current.md`.
- No bb-node source code has been changed as part of this integration.
- Verified:
  - strict validation passed with 0 invalid checkpoints;
  - resume_snapshot successfully restored and displayed the current handoff;
  - checkpoint content is readable independently of the current chat session.
- Remaining verification:
  - whether the checkpoint should be committed to the branch;
  - whether Codex/opencode automatically discover the installed global skills in their own runtime environments.

## Next Step
1. Review the final checkpoint content and Git diff.
2. Confirm only `.agents/checkpoints/current.md` is intended for this integration commit.
3. Never use `git add .`; stage only the intended checkpoint file if a commit is approved.
4. Commit the checkpoint only after explicit review/approval.
5. After the checkpoint is safely committed, separately verify cross-agent discovery/usage with Codex and opencode.

## Resume Recipe
- From repository root, run:
  `python3 ~/.agents/skills/repo-resume/scripts/resume_snapshot.py`
- Then read:
  `.agents/checkpoints/current.md`
  `.ai/CURRENT_STATE.md`
  `.ai/REQUIREMENTS.md`
  `.ai/DECISIONS.md`
  `.ai/` persistent task list
- Verify:
  `git status --short`
  `git branch --show-current`
- Treat `.ai/` as the durable project-memory source and this checkpoint as the current handoff snapshot.
- Verify Git state before editing.
- Do not touch the six pre-existing untracked local files unless the user explicitly instructs otherwise.

## Git Snapshot

### Working Tree
```text
?? .agents/checkpoints/current.md
?? core/collector.py.bak
?? events/engine_v3.py.bak
?? events/engine_v3.py.bak2
?? events/engine_v3.py.bak3
?? export_today.py
?? export_today.py.bak
```

### Recent Commits
```text
d0dccc2 chore: add AI project memory baseline
14c38d3 unify replay event calculation
5a01089 add replay engine v2
6fd0037 sync phone changes
74cff43 feat: add pipeline stale health checks
```
