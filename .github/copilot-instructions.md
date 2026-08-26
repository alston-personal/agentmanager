# AgentOS AI Contributor Instructions

You are working in the AgentOS logic/runtime repository.

## Read current reality first

Before architectural or cross-project changes, read in this order:

1. `README.md`
2. `docs/CURRENT_STATE.md`
3. `AGENTS.md`
4. `docs/AGENTOS_NODE.md` when capability ownership/resources are involved

Do not treat older pulse/brain-dump/LAMP-era documents as the current architecture when they conflict with the canonical current-state map and executable evidence.

## Essential invariants

- Preserve Logic/Data separation: mutable project/user state belongs under configured `AGENT_DATA_ROOT`, not accidentally in the logic repo.
- Resolve existing capability responsibility before creating a competing implementation.
- Newer user intent must not be rolled back by stale state, replay, compaction, or tool results.
- Evidence does not silently rewrite intent.
- Distinguish **Implemented**, **Verified**, and **Research** claims.
- Cognitive IR / arbitrary zero-cost cross-model switching remains research until repeatable tests prove it.

## Documentation reality

Architecture-sensitive implementation changes must update `README.md`, `ONBOARDING.md`, `AGENTS.md`, or `docs/CURRENT_STATE.md` in the same change set.

Run:

```bash
python3 scripts/documentation_reality_guard.py
```

Treat a documentation-drift failure as a regression.
