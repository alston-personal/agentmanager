# AgentOS Onboarding

> **Read this together with [`docs/CURRENT_STATE.md`](docs/CURRENT_STATE.md).** That file is the canonical implementation-reality map.

AgentOS is no longer accurately described as only a memory/pulse system. The current architecture includes continuation-state reconciliation, a persistent control plane, governance/resource resolution, cross-node Realm surfaces, platform drivers, and evidence-first acceptance.

## Start here

For an agent or engineer entering this repository:

1. Read `README.md` for the product goal and public architecture.
2. Read `docs/CURRENT_STATE.md` to distinguish **implemented**, **verified**, and **research** capabilities.
3. Read `AGENTS.md` for repository-specific operating constraints.
4. For cross-project/system work, read `docs/AGENTOS_NODE.md` and resolve existing responsibility before inventing a new provider.
5. Use tests and `.agentos/evidence/` to verify claims instead of trusting stale prose.

## Current mental model

```text
Durable state / handoffs / registries / evidence
                    │
                    ▼
                 AgentOS
     ┌──────────────┼──────────────┐
 continuation   control plane   governance/resources
     │              │              │
     └──────────────┼──────────────┘
                    ▼
        replaceable model / agent / node
```

The long-term objective is functional continuity across executors: changing model/session/machine should not force a user to reconstruct the project manually.

## Current implemented entry points

- `scripts/continuation_state.py` — protects newer user intent from stale replay/compaction rollback.
- `agent_core/control_plane.py` — persistent node/task coordination and leasing.
- `agent_core/session_lifecycle.py` + `runtime_core/` — host-neutral session close/handoff persistence.
- `scripts/agentos_node.py` — node-local capability/governance/resource discovery surface.
- `agent_core/governance_directory.py` — responsibility/provider resolution.
- `agent_core/resource_registry.py` — registered world/resource state.
- `agent_core/realm_fabric.py` / `realm_server.py` — cross-node Realm work.
- `agent_core/platform/` — Linux/Windows/macOS runtime abstraction.
- `.agentos/evidence/` — live acceptance and operational receipts/evidence.

## Research boundary

**Cognitive IR / portable working-state reconstruction remains research.** Do not claim that AgentOS can already transfer hidden activations or guarantee zero-cost switching between arbitrary models. The active research goal is to find a model-independent representation that can reconstruct enough working state for another executor to continue functionally.

## Logic / Data separation

The original separation remains an invariant, but it is a foundation rather than the full architecture:

- logic/runtime semantics live in this repository;
- mutable project state, memory, handoffs, and registries belong in the configured `AGENT_DATA_ROOT`;
- environment-specific absolute paths are examples, not protocol semantics.

## Verification

Useful narrow checks:

```bash
python3 scripts/continuation_state.py --self-test
python3 -m unittest tests.test_continuation_state tests.test_control_plane -v
python3 scripts/documentation_reality_guard.py
```

For node governance/resource contracts, see `docs/AGENTOS_NODE.md` and the governance audit workflow.

## Documentation freshness rule

Architecture-sensitive code changes must update an authoritative entry-point document in the same change set. CI enforces this through `.github/workflows/documentation-reality-guard.yml`.

If this file and implementation disagree, implementation plus executable tests/evidence wins and this file must be corrected immediately.
