# Branch Consolidation Audit — 2026-08-24

## Canonical development line

- Stable baseline: `main`
- AgentOS vNext integration branch: `feature/distributed-agentos-runtime`
- New AgentOS vNext work must continue on the integration branch unless a short-lived child branch is explicitly declared with parent, merge target, purpose, and completion condition.
- GitHub writes must always specify the branch explicitly. Default-branch fallback is prohibited for experimental work.

## Branch classification

| Branch | Relationship to integration branch | Verdict |
|---|---|---|
| `feature/state-kernel-v2` | 0 ahead; already merged through PR #3 | RETIRE |
| `feature/watchdog-backoff` | 0 ahead / 536 behind | RETIRE |
| `feature/node-cognitive-bridge-v0` | wrong lineage; only accidental Oracle probe/evidence delta | RETIRE after evidence reconciliation |
| `agent/auto-pushing` | 4 commits ahead / ~500 behind | SELECTIVE SALVAGE, then RETIRE |

## `agent/auto-pushing` salvage audit

The branch's four unique commits are historical hashes, but unique commit identity does not imply unique current semantics. Each was checked against the current integration branch.

### `de14ab4` — hybrid git push policy for agent-data

**Verdict: semantic content already present; do not cherry-pick.**

The current integration branch's `scripts/meditation/meditator.py` already performs post-meditation Data Layer status/commit/pull/push behavior. Replaying the old commit would duplicate or regress newer memory routing and secret-sanitization changes.

### `ac1b7b1` — watchdog service check + selective project indexing

**Verdict: semantic content already present; do not cherry-pick.**

Current integration branch already contains `check_os_watchdog()` in `scripts/maintenance.py` and the full `scripts/toggle_project_indexing.py` tool. The old commit hash is unique, but its useful behavior has been incorporated by later development.

### `7e649b4` — merge of historical main into legacy branch

**Verdict: historical merge only; do not transplant.**

This merge carried portability/workspace/schedule changes from the historical main line. Current vNext has evolved far beyond that baseline. Cherry-picking a merge commit would reintroduce stale topology and is not a valid consolidation strategy.

### `3eff783` — local config and Lobster adjustments

**Verdict: mixed/stale; do not cherry-pick wholesale. Selective salvage only.**

The commit mixes machine-local workspace entries, schedule changes, role/persona routing, physical-output verification, direct executor changes, local path assumptions, and other runtime behavior. Several parts are tightly coupled to the older Lobster architecture and would bypass or conflict with current Canonical IR / Control Plane / Governance execution semantics.

One clearly independent reusable asset was absent from vNext: the Redmine 2.6 -> 5 porting skill. It has been salvaged into the integration branch as:

- `.agent/skills/redmine-26-to-5-port/SKILL.md`
- `.agent/skills/redmine-26-to-5-port/references/porting-pitfalls.md`
- `.agent/skills/redmine-26-to-5-port/agents/openai.yaml`

No other `3eff783` runtime/config delta is approved for transplant without a new task-specific review.

## Consolidation result

`agent/auto-pushing` now has no known unsalvaged change that should be merged wholesale into AgentOS vNext. Its useful isolated Redmine knowledge has been preserved, while stale runtime/config behavior is intentionally rejected.

The repository should therefore be mentally modeled as:

```text
main                              stable / production baseline
  \
   feature/distributed-agentos-runtime   canonical AgentOS vNext continuation line
```

Historical branches may remain physically visible until deletion tooling or an explicit cleanup action is used, but they are not valid continuation targets.

## Fresh-agent startup rule

Before making changes, a fresh executor must read:

1. `AGENTS.md`
2. `.agentos/development-context.json`
3. this audit when branch history is relevant
4. Canonical IR / Control Plane state when reachable

Do not infer the active development branch from the current checkout alone. The canonical development context is authoritative for development-line policy; Canonical IR remains authoritative for goal/task continuity.
