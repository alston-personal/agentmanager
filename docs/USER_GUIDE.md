# AgentOS User Guide

AgentOS is an evolving AI-agent runtime/control-plane project whose continuity goal is simple:

> Switch session, model, executor, or machine without manually rebuilding the work from raw chat history.

For the current implementation boundary, always read [`CURRENT_STATE.md`](CURRENT_STATE.md). It distinguishes **Implemented**, **Verified**, and **Research** capabilities.

## Core architecture

AgentOS keeps durable state outside a single model/session. The current repository includes explicit continuation reconciliation, persistent coordination, session handoff records, governance/resource discovery, cross-node Realm surfaces, platform drivers, and committed operational evidence.

Logic/Data separation remains foundational:

- **Logic:** code, runtime semantics, workflows, tests, governance contracts (`agentmanager`).
- **Data/State:** mutable project state, memory, handoffs, registries, and records (`AGENT_DATA_ROOT`).

## Common operations

### Verify continuity semantics

```bash
python3 scripts/continuation_state.py --self-test
python3 -m unittest tests.test_continuation_state tests.test_control_plane -v
```

The current continuation reconciler protects an important invariant: newer user goals/corrections must not be rolled back by stale replay or old tool results.

### Inspect node capabilities / responsibility

For a configured AgentOS node:

```bash
agentos-node harvest
agentos-node governance resolve capability://network.port.allocate
agentos-node resource list --kind site
```

See `docs/AGENTOS_NODE.md` for the current node contract.

### Check documentation reality

```bash
python3 scripts/documentation_reality_guard.py
```

Architecture-sensitive changes are also checked in GitHub Actions. Documentation drift is treated as a regression.

### Check runtime/platform setup

See:

- `docs/PLATFORM_DRIVERS.md`
- `docs/RESTORE_NEW_MACHINE.md`
- `scripts/platform_runtime.py`
- `scripts/install_services.py`

Do not assume a Linux `/home/ubuntu/...` path is universal; deployment paths are environment-specific.

## Evidence and truth hierarchy

When a prose document conflicts with the repository:

1. executable implementation;
2. tests and committed operational evidence;
3. `docs/CURRENT_STATE.md`;
4. other narrative/history documents.

The mismatch must then be corrected rather than preserved indefinitely.

## Research: cross-model Cognitive IR

AgentOS does **not** currently claim that hidden model activations can be copied between arbitrary models. The active research question is whether a model-independent working-state representation can preserve enough position, intent, constraints, decisions, rejected paths, and next direction that another model can functionally continue from a relative instruction such as `continue`.

Until repeatable cross-model experiments prove that layer, treat it as research rather than a shipping capability.
