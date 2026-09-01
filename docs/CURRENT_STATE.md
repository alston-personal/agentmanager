# AgentOS Current Architecture & Reality

**Status date:** 2026-09-01  
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
| Governance responsibility resolution | Implemented + tested | `agent_core/governance_directory.py` | `tests/test_governance_directory.py`, governance audit workflow/evidence |
| Resource registry / world-state lookup | Implemented + tested | `agent_core/resource_registry.py` | `tests/test_resource_registry.py` |
| Realm / cross-node fabric | Implemented slices + tested | `agent_core/realm_fabric.py`, `agent_core/realm_server.py`, `agent_core/realm_cli.py` | `tests/test_realm_fabric.py`, `.agentos/commands/` |
| Platform driver abstraction | Implemented + tested | `agent_core/platform/`, `scripts/platform_runtime.py` | `tests/test_platform_runtime.py` |
| ChatGPT bootstrap transport into ONE | Implemented bootstrap; live regression still required | Bootstrap Control Inbox #50 → Oracle bridge → ONE | Issue #50 control command/result evidence; `docs/CHATGPT_ONE_TRANSPORT.md` |
| Authority-driven transport routing | Implemented + tested candidate | `agent_core/transport_routing.py`, `governance/transport-routing.json` | `tests/test_transport_routing.py`; fresh ChatGPT session acceptance pending in #179 |
| Antigravity Gemini ONE MCP awareness | Implementation candidate / not accepted | PR #167 `agentos_node/one_mcp.py` | fresh built-in Gemini E2/E3 acceptance still pending |
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

### Capability does not imply authority

The presence of a mutation tool, a mergeable pull request, a reachable Actions runner, or passing CI does not create authority for a different class of operation. Agents must stop at `AWAITING_HUMAN_APPROVAL` for protected publication, and control-plane work must not opportunistically switch to GitHub Actions because ONE-side transport is unavailable.

See `.agent/governance/protected_branches.yaml`, `docs/governance/decisions/GOV-2026-08-27-001-protected-branch-authority.md`, and `docs/CHATGPT_ONE_TRANSPORT.md`.

### Transport failure does not expand authority

For typed Realm/Node/control-plane intents, the authorized transport order is direct ONE → AgentOS MCP/App → Bootstrap Control Inbox. GitHub Actions is not in that allowlist and is not a failure fallback. GitHub Actions is reserved for explicitly typed workflow intents such as CI/tests, build/package, release, deployment, or separately authorized evidence workflows.

The current ChatGPT Web path is therefore not yet a native direct ONE connection. It is a bootstrap path through GitHub comments into an Oracle bridge and then ONE. The GitHub mailbox is transport only; ONE remains the control-plane authority. The target is to replace that mailbox with an AgentOS MCP/App after equivalent acceptance evidence exists.

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

Those mechanisms are historical foundations, not an adequate description of current AgentOS. Current code additionally contains explicit continuation reconciliation, a persistent control plane, node/capability governance, resource state, Realm cross-node execution, platform abstractions, committed execution evidence, documentation reality checks, explicit authority boundaries for protected mutations, and an explicit transport-authority contract that prevents workflow-carrier capability from becoming control-plane authority.

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
