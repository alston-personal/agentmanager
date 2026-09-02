# AgentOS Current Architecture & Reality

**Status date:** 2026-09-02  
**Purpose:** canonical public map of what is implemented, what is verified, and what is still research.

This document exists to prevent architecture drift between code and prose. It is intentionally narrower than a roadmap: every item marked **Implemented** must have a concrete repository path; every item marked **Verified** must also have a test or evidence path.

## Product goal

AgentOS has one continuity goal:

> A user should be able to switch session, model, executor, extension, or machine and continue useful work without manually reconstructing the project from a large conversation history.

This goal is broader than memory retrieval. AgentOS treats durable project/working state as an external system concern and treats models/executors/extensions as replaceable clients of that state.

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
| Governance drift guard | Implemented + tested | `scripts/drift_guard.py`, constitution/role registries | `tests/test_drift_guard.py` |
| Protected-branch authority guard | Implemented on governance branch | `.agent/governance/protected_branches.yaml`, `scripts/protected_branch_authority.py` | `tests/test_protected_branch_authority.py`, `docs/governance/decisions/GOV-2026-08-27-001-protected-branch-authority.md` |
| Evidence-first operational acceptance | Implemented | `.agentos/evidence/` | live acceptance files committed by workflows and live executor evidence |
| Documentation Reality Guard | Implemented | `scripts/documentation_reality_guard.py` | `.github/workflows/documentation-reality-guard.yml`, `tests/test_documentation_reality_guard.py` |
| Canonical continuation IR (`agentos.ir/v1`) | Implemented + verified for AgentOS Core E2/E3 slices | `agent_core/project_continuation_index.py`, `agent_core/resolve_facade.py`, Gemini/Codex consumers | Gemini E2 evidence plus `.agentos/evidence/issue-152-codex-extension-e3-verified-2026-09-02.md` |
| Guarded Canonical IR handoff / parent fence | Implemented + tested | `agent_core/canonical_ir_handoff.py`, guarded `agent_core/project_continuation_index.py` | `tests/test_canonical_ir_handoff.py`, `tests/test_project_continuation_index.py` |
| ONE active Canonical continuation selector | Implemented + verified for tested Gemini/Codex continuity slice | `agent_core/active_continuation.py`, `scripts/seed_active_continuation.py`, Gemini PreInvocation + Codex MCP consumers | unrelated-workspace Oracle probe plus two fresh Codex `one_resolve_active` observations |
| Fresh Antigravity Gemini continuation with only `繼續` | Verified for one concrete E2 slice | Oracle Gemini-side `PreInvocation` hydration from ONE Canonical IR plus read-only MCP adapter | two independent fresh Gemini sessions reproduced `ONE_PREINVOCATION_IR / agentos-core / idx-core-152 / ir-core-152`; see `.agentos/evidence/issue-152-antigravity-gemini-e2-2026-09-01.md` |
| OpenAI Codex IDE extension ONE bootstrap | Implemented + live-verified | `agentos_node/codex_one_mcp_stdio.py`, `scripts/install_codex_one_oracle.py`, global `~/.codex/AGENTS.md` + `~/.codex/config.toml` managed blocks | two independent fresh Codex extension threads resolved the same ONE-selected E3 generation; `.agentos/evidence/issue-152-codex-extension-e3-verified-2026-09-02.md` |
| Gemini extension → ONE → OpenAI Codex IDE extension E3 | **Verified for one concrete Oracle cross-extension slice** | corrected child handoff, Codex native AGENTS+MCP bootstrap, `one_resolve_active` receipt | #152 comments `5503435564` + `5503469931`; distinct receipt timestamps `02:28:29Z` and `02:32:25Z`; repository evidence file above |
| Post-E3 canonical continuation | Implemented guarded handoff; live advancement pending | `scripts/advance_issue_152_after_e3_verified.py`, `scripts/advance_issue_152_after_e3_verified_oracle.sh` | parent-fenced from verified E3 generation; intended to resume broader #152 work instead of repeating completed regression |
| Model-independent Cognitive IR across arbitrary executors/models/extensions | Research | bounded `agentos.ir/v1` continuity now has one verified Gemini→Codex cross-extension slice, but general cross-client projection/benchmark is not canonical | requires broader model/extension/machine experiments; do not generalize one verified slice |
| General zero-cost model/executor/extension/machine switch with only `continue` | Target / not yet proven generally | Gemini E2 and Gemini→Codex E3 are verified concrete slices | broader continuity, client diversity, and machine portability benchmarks still required |

## Important invariants

### Newer user intent must never be rolled back

Compaction, replay, stale tool results, or executor switching must not replace a newer goal/correction with an older one. `scripts/continuation_state.py` currently protects this narrow invariant and has regression tests.

### Canonical IR advancement is parent-fenced

A writer advancing an existing Canonical IR generation must supply the exact current `index_id` and `ir_id`, create a new generation, and set the new IR's `parent_ir_id` to that expected parent. The comparison occurs while holding the same continuation-index lock used for publication. A concurrent or stale writer therefore fails before mutation instead of overwriting newer continuation state.

### Active selector is a pointer, not another state store

`agentos.active-continuation/v1` stores only `project_id + index_id + ir_id` (plus activation metadata). It does not duplicate goal, decisions, tasks, evidence, or model context. Those remain in the referenced Canonical IR. Selector reads revalidate the referenced generation; a stale selector fails closed.

The current publisher is still restricted to `agentos-core`, so bootstrap may initialize a missing selector from that one supported canonical project. It must not silently overwrite an existing stale selector.

### Workspace is not continuation authority

The IDE's workspace must not choose durable continuation. This is evidence-backed: early E3 attempts continued local `if-tv-station` and ACAS work because continuation hydration was gated by workspace state. Supporting more workspace path shapes did not solve the problem; the workspace gate itself was architecturally wrong.

Fresh client hydration now selects state from the ONE active selector. Workspace metadata may describe where execution occurs, but it cannot replace Canonical IR or silently switch project state.

### Extension lifecycle is not shared by assumption

Antigravity Gemini and the OpenAI Codex IDE extension are separate clients/extensions. `~/.gemini/config/hooks.json` is a Gemini-side lifecycle hook and is not evidence that a Codex extension thread was invoked or hydrated.

The Codex extension uses its own native bootstrap surfaces: Codex home `AGENTS.md` instructions and Codex MCP configuration. Cross-extension continuity must be proven at each client's actual lifecycle boundary instead of assuming one extension's hook intercepts another.

### Bootstrap instructions are not another state store

Gemini hook rules, Codex `AGENTS.md`, and MCP config contain discovery/authority instructions only. They must not copy the current goal/decisions/tasks/IR generation body into client-specific config. The authoritative working state remains ONE Canonical IR, selected by the active pointer.

### Evidence is not intent

Tool results and execution evidence can inform decisions, but they do not silently rewrite the user's active goal. Handoff evidence is bounded and credential-field checked before it can enter Canonical IR.

### Capability does not imply authority

The presence of a mutation tool, a mergeable pull request, a reachable Actions runner, or passing CI does not create authority for a different class of operation. Agents must stop at `AWAITING_HUMAN_APPROVAL` for protected publication, and control-plane work must not opportunistically switch to GitHub Actions because ONE-side transport is unavailable.

See `.agent/governance/protected_branches.yaml`, `docs/governance/decisions/GOV-2026-08-27-001-protected-branch-authority.md`, and `docs/CHATGPT_ONE_TRANSPORT.md`.

### Transport failure does not expand authority

For typed Realm/Node/control-plane intents, the authorized transport order is direct ONE → AgentOS MCP/App → Bootstrap Control Inbox. GitHub Actions is not in that allowlist and is not a failure fallback. GitHub Actions is reserved for explicitly typed workflow intents such as CI/tests, build/package, release, deployment, or separately authorized evidence workflows.

The current ChatGPT Web path is therefore not yet a native direct ONE connection. It is a bootstrap path through GitHub comments into an Oracle bridge and then ONE. The GitHub mailbox is transport only; ONE remains the control-plane authority. The target is to replace that mailbox with an AgentOS MCP/App after equivalent acceptance evidence exists.

### Discover before invent

Reusable/cross-project work should resolve existing responsibility and resources before creating parallel implementations. See `docs/AGENTOS_NODE.md` and the Governance Directory.

### Models are executors, not the durable source of truth

AgentOS does not assume access to model activations or model-specific internal state. Durable coordination and continuity state must remain external and transportable. Executors may report evidence, but Core-owned governed writers advance canonical state.

## What changed from the early AgentOS architecture

Early documentation centered on:

- `SHORT_TERM.md` / `LONG_TERM.md`;
- pulse files and brain dumps;
- manual `/report` handoff;
- Logic/Data separation as the main architectural idea.

Those mechanisms are historical foundations, not an adequate description of current AgentOS. Current code additionally contains explicit continuation reconciliation, a persistent control plane, node/capability governance, resource state, Realm cross-node execution, platform abstractions, committed execution evidence, documentation reality checks, explicit authority boundaries for protected mutations, an explicit transport-authority contract, a bounded Canonical IR continuation path, and a distinct ONE active-continuation pointer that selects which canonical generation a fresh client should hydrate.

Old documents that describe only the memory/pulse era must be treated as historical unless they link back to this file.

## Current research boundary: Cognitive IR

AgentOS has a concrete bounded Canonical IR path for project continuation: `agentos.ir/v1` can be published together with an `agentos.execution-head/v1` generation fence and hydrated into a fresh Antigravity Gemini session through ONE. That E2 path is implemented and live-verified.

The same bounded path has a Core-owned guarded handoff writer. Advancing a head requires the exact previous `index_id` / `ir_id` under the publication lock, preserving authoritative constraints/decisions and appending bounded sanitized evidence into a child IR generation.

The early E3 failures revealed two independent bootstrap problems. First, workspace membership cannot choose continuation; this led to the ONE active-selector design. Second, Antigravity Gemini and OpenAI Codex are separate extensions with separate lifecycle surfaces. A Gemini `PreInvocation` attestation therefore cannot prove a Codex extension invocation.

The corrected E3 design preserves one canonical state while giving each client its native discovery path:

```text
Antigravity Gemini extension
        ↓ Gemini PreInvocation
ONE active selector → Canonical IR
        ↑ one_resolve_active
OpenAI Codex IDE extension
        ↑ Codex AGENTS.md + MCP bootstrap
```

This concrete E3 slice is now live-verified from two independently fresh Codex IDE extension threads, each given only `繼續`, with independent terminal receipts proving `one_resolve_active` reached the same corrected Canonical IR generation and `credential_exposed=false`. No client-specific bootstrap file contained a copied IR body.

This is meaningful evidence for the model-independent working-state hypothesis, but it is not proof of arbitrary portability. The unresolved research question remains broader: whether one model-independent working-state representation and projection layer can preserve useful continuity across arbitrary model families, executors, extensions, and machines with consistently low reconstruction cost. Public model interfaces do not provide a portable common activation state, and different clients need not expose the same lifecycle hooks.

The active hypothesis remains:

```text
full session / events
       ↓ encode/update
model-independent working-state IR
       ↓ active generation selector
       ↓ client-native hydrate/project
new model / executor / extension
       ↓
functional continuation
```

Success means the new executor can preserve the current goal, established decisions/constraints, rejected paths, open questions, and next direction well enough that a relative instruction such as `continue` remains meaningful.

Do not generalize the verified Gemini→Codex E3 slice into a claim of arbitrary cross-model continuity. The next #152 engineering step is the broader Node/executor lifecycle extraction and remaining real-client acceptance; the next research step is to repeat the continuity pattern across additional clients/models/machines.

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
