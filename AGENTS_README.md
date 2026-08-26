# AgentOS — Cross-Agent Continuity Guide

> **Current architecture:** read `README.md`, `docs/CURRENT_STATE.md`, and `AGENTS.md` first.

This file used to describe the early LAMP / pulse / brain-dump architecture as if it were the whole AgentOS. That is no longer accurate. Those mechanisms are historical continuity techniques; current AgentOS also contains explicit continuation-state reconciliation, a persistent control plane, governance/resource resolution, Realm cross-node execution, platform drivers, and evidence-first validation.

## Agent entry protocol

When an AI agent enters this repository:

1. Read `docs/CURRENT_STATE.md` to learn what is actually implemented vs. still research.
2. Read `AGENTS.md` for current repository constraints.
3. For system/cross-project changes, use the `agentos-node` responsibility/resource flow from `docs/AGENTOS_NODE.md`.
4. Inspect tests and `.agentos/evidence/` when validating a capability claim.
5. Do not infer the current architecture from old pulse files, brain dumps, or a single historical handoff document.

## Continuity principle

The system is moving from "remember the previous conversation" toward "preserve enough durable working state that another executor can continue." A newer user goal/correction must survive stale tool results, compaction, replay, and executor changes.

The model-independent **Cognitive IR** layer is an active research direction, not a completed feature. Do not claim arbitrary ChatGPT/Gemini/Claude switching is solved unless a repeatable benchmark proves it.

## Persistent state

Logic/Data separation remains mandatory:

- runtime logic, tests, workflows, and contracts live in `agentmanager`;
- mutable project state, memory, handoffs, and registries live under the configured `AGENT_DATA_ROOT`;
- absolute paths such as `/home/ubuntu/...` are deployment examples, not universal protocol requirements.

## Documentation rule

If architecture-sensitive implementation changes, update an authoritative document in the same change set and run:

```bash
python3 scripts/documentation_reality_guard.py
```

Do not let this file become a second competing source of truth. `docs/CURRENT_STATE.md` is the canonical public implementation-reality map.
