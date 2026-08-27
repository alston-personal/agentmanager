# AgentOS Current Architecture & Reality

**Status date:** 2026-08-27  
**Purpose:** canonical public map of what is implemented, what is verified, and what is still research.

This document exists to prevent architecture drift between code and prose. It is intentionally narrower than a roadmap: every item marked **Implemented** must have a concrete repository path; every item marked **Verified** must also have a test or evidence path.

## Product goal

AgentOS has one continuity goal:

> A user should be able to switch session, model, executor, or machine and continue useful work without manually reconstructing the project from a large conversation history.

This goal is broader than memory retrieval. AgentOS treats durable project/working state as an external system concern and treats models as replaceable executors.

## Reality map

| Capability | State | Implementation | Verification / evidence |
|---|---|---|---|
| Logic / data separation | Implemented | `agent_core/config.py`, bootstrap/runtime scripts | existing bootstrap/runtime tests |
| Session close / handoff record | Implemented | `agent_core/session_lifecycle.py`, `runtime_core/` | `tests/test_session_close.py` |
| Continuation-state monotonicity | Implemented + tested | `scripts/continuation_state.py` | `tests/test_continuation_state.py` |
| Persistent control plane | Implemented + tested | `agent_core/control_plane.py` | `tests/test_control_plane.py`, `.agentos/evidence/bootstrap-control-plane.txt` |
| Node registry / capability discovery | Implemented + tested | `agent_core/node_registry.py`, `scripts/agentos_node.py` | `tests/test_agentos_node.py`, `tests/test_node_registry_v01.py` |
| Node / executor separation | Implemented + tested on feature branch | `agentos_node/executor_registry.py`, `agentos_node/executor_bridge.py`, `agentos_node/thin_client.py` | `tests/test_executor_registry.py`, `tests/test_executor_bridge.py`, `Node Executor Runtime CI` |
| Windows always-on Node Runtime carrier | Implemented, not yet live-verified | `scripts/windows/install_node_runtime_service.ps1` | Windows-native syntax CI; requires live `vopc5750` heartbeat acceptance |
| Windows interactive Desktop executor carrier | Implemented, not yet live-verified | `agentos_node/desktop_executor_host.py`, `agentos_node/desktop_executor_cli.py`, `scripts/windows/install_desktop_executor_user.ps1` | bridge/unit tests + Windows-native syntax CI; requires live desktop acceptance |
| Governance responsibility resolution | Implemented + tested | `agent_core/governance_directory.py` | `tests/test_governance_directory.py`, governance audit workflow/evidence |
| Resource registry / world-state lookup | Implemented + tested | `agent_core/resource_registry.py` | `tests/test_resource_registry.py` |
| Realm / cross-node fabric | Implemented slices + tested | `agent_core/realm_fabric.py`, `agent_core/realm_server.py`, `agent_core/realm_cli.py` | `tests/test_realm_fabric.py`, `.agentos/commands/` |
| Platform driver abstraction | Implemented + tested | `agent_core/platform/`, `scripts/platform_runtime.py` | `tests/test_platform_runtime.py` |
| Governance drift guard | Implemented + tested | `scripts/drift_guard.py`, constitution/role registries | `tests/test_drift_guard.py` |
| Protected-branch authority guard | Implemented on governance branch | `.agent/governance/protected_branches.yaml`, `scripts/protected_branch_authority.py` | `tests/test_protected_branch_authority.py`, `docs/governance/decisions/GOV-2026-08-27-001-protected-branch-authority.md` |
| Evidence-first operational acceptance | Implemented | `.agentos/evidence/` | live acceptance files committed by workflows |
| Documentation Reality Guard | Implemented | `scripts/documentation_reality_guard.py` | `.github/workflows/documentation-reality-guard.yml`, `tests/test_documentation_reality_guard.py` |
| Model-independent Cognitive IR | Research | schema/experiments not yet canonical | requires cross-model continuity experiment |
| Zero-cost model switch with only `continue` | Target / not yet proven generally | depends on future portable working-state layer | continuity benchmark still required |

## Important invariants

### Newer user intent must never be rolled back

Compaction, replay, stale tool results, or executor switching must not replace a newer goal/correction with an older one. `scripts/continuation_state.py` currently protects this narrow invariant and has regression tests.

### Evidence is not intent

Tool results and execution evidence can inform decisions, but they do not silently rewrite the user's active goal.

### Node identity is not executor availability

A Node is the durable transport/control-plane participant. Executors are capability providers attached to that Node and may independently become available or unavailable. In particular, Windows being online must not imply that an interactive desktop is available. A Session 0 Node Runtime must remain able to heartbeat, receive work, report executor status, and recover even when the Desktop executor is absent.

The Windows Desktop executor is intentionally hosted in the logged-in user session. Its interactive Scheduled Task is an executor carrier only; it must not own the Realm transport credential or become the Node's liveness boundary. The always-on Node Runtime belongs to the Windows Service carrier.

### Capability does not imply authority

The presence of a mutation tool, a mergeable pull request, or passing CI does not authorize a protected-branch mutation. Agents must stop at `AWAITING_HUMAN_APPROVAL` until an explicit human authorization exists. See `.agent/governance/protected_branches.yaml` and `docs/governance/decisions/GOV-2026-08-27-001-protected-branch-authority.md`.

### Discover before invent

Reusable/cross-project work should resolve existing responsibility and resources before creating parallel implementations. See `docs/AGENTOS_NODE.md` and the Governance Directory.

### Models are executors, not the durable source of truth

AgentOS does not assume access to model activations or model-specific internal state. Durable coordination and continuity state must remain external and transportable.

## What changed from the early AgentOS architecture

Early documentation centered on:

- `SHORT_TERM.md` / `LONG_TERM.md`;
- pulse files and brain dumps;
- manual `/report` handoff;
- Logic/Data separation as the main architectural idea.

Those mechanisms are historical foundations, not an adequate description of current AgentOS. Current code additionally contains explicit continuation reconciliation, a persistent control plane, node/capability governance, resource state, Realm cross-node execution, platform abstractions, committed execution evidence, documentation reality checks, and explicit authority boundaries for protected mutations.

Old documents that describe only the memory/pulse era must be treated as historical unless they link back to this file.

## Current research boundary: Cognitive IR

The unresolved question is not how to copy one model's hidden state into another model. Public model interfaces do not provide a portable common activation state, and different models need not have identical internal representations.

The active hypothesis is instead:

```text
full session / events
       ↓ encode/update
model-independent working-state IR
       ↓ hydrate/project
new model / executor
       ↓
functional continuation
```

Success means the new executor can preserve the current goal, established decisions/constraints, rejected paths, open questions, and next direction well enough that a relative instruction such as `continue` remains meaningful.

This layer is **not yet declared implemented**. Do not describe it as a finished feature until a repeatable cross-model continuity benchmark exists.

## Documentation ownership rule

`README.md`, `ONBOARDING.md`, `AGENTS.md`, and this file are authoritative entry points. Architecture-sensitive implementation changes must update at least one of these files in the same change set.

The CI guard watches changes under core surfaces including:

- `agent_core/`
- `runtime_core/`
- `scripts/continuation_state.py`
- `scripts/agentos_node.py`
- `scripts/drift_guard.py`
- `.agent/CONSTITUTION.yaml`
- `.agent/roles/`
- `.agent/governance/`
- `.agentos/commands/`
- relevant architecture workflows

A code-only architecture change should fail CI until documentation is updated.

## Updating this document

When a capability moves between **Research → Implemented → Verified**, update the table with concrete implementation and verification paths. Never promote a capability based only on discussion or a roadmap.

When implementation contradicts this file, fix the file immediately; do not preserve an obsolete narrative for continuity's sake.
