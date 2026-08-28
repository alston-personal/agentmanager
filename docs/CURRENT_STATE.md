# AgentOS Current Architecture & Reality

**Status date:** 2026-08-28  
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
| Canonical Project Identity | Implemented + tested | `agent_core/project_store.py`, `agent_core/resolve_facade.py` | `tests/test_project_store_canonical.py`, governed Core registration workflow/evidence |
| Node registry / capability discovery | Implemented + tested | `agent_core/node_registry.py`, `scripts/agentos_node.py` | `tests/test_agentos_node.py`, `tests/test_node_registry_v01.py` |
| Governance responsibility resolution | Implemented + tested | `agent_core/governance_directory.py` | `tests/test_governance_directory.py`, governance audit workflow/evidence |
| Resource registry / world-state lookup | Implemented + tested | `agent_core/resource_registry.py` | `tests/test_resource_registry.py` |
| Realm / cross-node fabric | Implemented slices + tested | `agent_core/realm_fabric.py`, `agent_core/realm_server.py`, `agent_core/realm_cli.py` | `tests/test_realm_fabric.py`, `.agentos/commands/` |
| Controller dispatch route | Implemented + live accepted | Realm server / ControllerService path | `.agentos/evidence/issue-64/control-inbox.json`; real Control Inbox acceptance reached ControllerService |
| Core deployment authority / generation fence | Implemented + live accepted | governed claim/install/release path, Action Relay deployment fence | `docs/CORE_DEPLOYMENT_AUTHORITY.md`, active-lease conflict proof, Issue #64 acceptance |
| Platform driver abstraction | Implemented + tested | `agent_core/platform/`, `scripts/platform_runtime.py` | `tests/test_platform_runtime.py` |
| Governance drift guard | Implemented + tested | `scripts/drift_guard.py`, constitution/role registries | `tests/test_drift_guard.py` |
| Protected-branch authority guard | Implemented on governance branch | `.agent/governance/protected_branches.yaml`, `scripts/protected_branch_authority.py` | `tests/test_protected_branch_authority.py`, `docs/governance/decisions/GOV-2026-08-27-001-protected-branch-authority.md` |
| Evidence-first operational acceptance | Implemented | `.agentos/evidence/` | live acceptance files committed by workflows |
| Documentation Reality Guard | Implemented | `scripts/documentation_reality_guard.py` | `.github/workflows/documentation-reality-guard.yml`, `tests/test_documentation_reality_guard.py` |
| Model-independent Cognitive IR | Research | operational handoff envelopes exist, but general sufficiency is not canonical | requires repeatable cross-model continuity benchmark |
| Zero-cost model switch with only `continue` | Target / not yet proven generally | depends on portable working-state + canonical resolution layer | continuity benchmark still required |

## Canonical Project Identity contract

Project identity is now explicitly separated from repository, checkout path, runtime path, deployment target, and state storage.

The canonical project document uses schema:

```text
agentos.project/v1
```

and includes at minimum:

```text
project_id
display_name
aliases
source.repo
source.branch
source.canonical_path
source.node
state.data_path
state.document
```

`project_id` is a stable logical identity. It must not be derived from a repository name or checkout directory. Compatibility fields such as `repo_url`, `actual_code_path`, and `data_path` are projections for older readers; they are not separate authority sources.

Registration projects the same identity into Governance Directory as `project://<project_id>` with explicit project/source/state authority. Canonical resolution must reject mutation when source authority is incomplete or integrity checks fail.

## Realm Node Map and capability semantics

The Realm Node Map is persistent ONE-side state. A node record may include heartbeat freshness, reported/effective status, capabilities, tool presence, and surface inventory.

Important distinctions:

- a conceptual/logical surface is not automatically an enrolled live node;
- a capability advertised by a node is not authority to execute it;
- transport reachability is not the same as capability availability;
- reaching ControllerService and receiving a node-level capability error proves the Core dispatch route is alive even though the target node is not yet ready for that action.

The authoritative live node count/status comes from the runtime NodeRegistry, not from architecture diagrams or conversation assumptions.

## Core runtime authority status

Realm Fabric is a single live Core service governed by canonical deployment state in:

```text
/home/ubuntu/agent-data/governance/core-deployment.json
```

The deployment state tracks desired/observed commit, monotonic generation, lease owner/expiry, and deployment status. A live generation is converged only when desired and observed commits match and status is `converged`.

A deployment claim and an installation are separate operations. Installation cannot silently advance generation. While a deployment lease is active, another generation advance is rejected even for the same owner; the current generation must first be released/expired according to the deployment contract. This prevents delayed or duplicated workflows from replacing an authoritative generation.

On 2026-08-28, Issue #64 final acceptance proved the real path:

```text
Bootstrap Control Inbox
  -> Oracle bridge / ONE
  -> POST /v1/controller/dispatch
  -> ControllerService
```

The accepted probe returned a node-level `NODE_CAPABILITY_NOT_ADVERTISED` outcome for `agent.surface.inspect`, rather than the former Core HTTP 404. This is the intended boundary: Core routing was restored; remaining capability convergence belongs to the Node Golden Path.

## Important invariants

### Newer user intent must never be rolled back

Compaction, replay, stale tool results, or executor switching must not replace a newer goal/correction with an older one. `scripts/continuation_state.py` currently protects this narrow invariant and has regression tests.

### Evidence is not intent

Tool results and execution evidence can inform decisions, but they do not silently rewrite the user's active goal.

### Capability does not imply authority

The presence of a mutation tool, a mergeable pull request, a node capability, or passing CI does not itself authorize mutation. Protected-branch, Core-deployment, project-source, and effect-level authority remain separate checks.

### Discover before invent

Reusable/cross-project work should resolve existing responsibility, project identity, node capability, and resources before creating parallel implementations. See `docs/AGENTOS_NODE.md` and the Governance Directory.

### Models are executors, not the durable source of truth

AgentOS does not assume access to model activations or model-specific internal state. Durable coordination and continuity state must remain external and transportable.

### Receipts are first-class evidence

A successful process start, health endpoint, or workflow status is not enough to claim end-to-end correctness. Architecture-sensitive acceptance should preserve capability/action receipts and, when relevant, real transport-path evidence under `.agentos/evidence/`.

## Memory and Cognitive IR boundary

Historical three-layer memory remains a useful conceptual model:

- L1: immediate/working state;
- L2: project/continuation state;
- L3: stable cross-project knowledge and learned patterns.

Current AgentOS no longer treats `SHORT_TERM.md` / `LONG_TERM.md` as the complete memory architecture. Canonical project state, continuation/work state, governance state, runtime state, receipts/evidence, and validated knowledge are distinct concerns.

An operational `agentos.ir/v1`-shaped continuation envelope may be used as a transport/handoff representation. That does **not** prove the stronger research claim that one model-independent Cognitive IR is generally sufficient for arbitrary cross-model continuation.

The active research hypothesis remains:

```text
canonical/project/memory/work state
       -> retrieve + reconcile + compile
       -> model-independent continuation IR
       -> executor adapter
       -> execution + receipts
       -> validated consolidation
```

Do not promote Cognitive IR from **Research** until a repeatable cross-model continuity benchmark demonstrates preservation of active goal, decisions/constraints, rejected paths, open questions, and next direction.

## Deprecated / historical paths

The following are historical foundations or compatibility surfaces and must not be described as current canonical architecture by themselves:

- `SHORT_TERM.md` / `LONG_TERM.md` as the whole memory system;
- pulse files / brain dumps as canonical state;
- manual `/report` as the sole handoff mechanism;
- repository name or checkout directory as Project Identity;
- direct GitHub/source-code rediscovery as the normal `continue <project>` path;
- process PID or `/health` alone as proof of a correct deployed Core generation;
- installer-side implicit generation advance;
- legacy Core deploy requests containing only `source_commit`;
- runtime-generation systemd drop-ins as authoritative generation state when canonical deployment state exists.

Compatibility readers may remain temporarily, but they are projections/adapters and must not acquire independent authority.

## Documentation ownership rule

`README.md`, `ONBOARDING.md`, `AGENTS.md`, `docs/CURRENT_STATE.md`, and `docs/CORE_CONTROL_ROOM.md` are authoritative entry points. Architecture-sensitive implementation changes must update at least one appropriate canonical document in the same change set.

The CI guard watches changes under core surfaces including `agent_core/`, `runtime_core/`, continuation/node/governance scripts, governance registries, `.agentos/commands/`, and relevant architecture workflows.

When implementation contradicts this file, fix the file immediately; do not preserve an obsolete narrative for continuity's sake.
