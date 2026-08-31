# AgentOS Current Architecture & Reality

**Status date:** 2026-08-31  
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
| Project release-lane authority | Implemented + tested | `.agent/governance/project_release_lanes.yaml`, `scripts/check_project_release_lane.py` | `tests/test_project_release_lane.py`, `Project Release Lane Guard` |
| Pinned project POC candidate deployment | Implemented for LayoutLib candidate path | `.github/workflows/oracle-release-layoutlab-v08-dev.yml` | release-lane static acceptance + public POC acceptance after dispatch |
| Node registry / capability discovery | Implemented + tested | `agent_core/node_registry.py`, `scripts/agentos_node.py` | `tests/test_agentos_node.py`, `tests/test_node_registry_v01.py` |
| Governance responsibility resolution | Implemented + tested | `agent_core/governance_directory.py` | `tests/test_governance_directory.py`, governance audit workflow/evidence |
| Resource registry / world-state lookup | Implemented + tested | `agent_core/resource_registry.py` | `tests/test_resource_registry.py` |
| Realm / cross-node fabric | Implemented slices + tested | `agent_core/realm_fabric.py`, `agent_core/realm_server.py`, `agent_core/realm_cli.py` | `tests/test_realm_fabric.py`, `.agentos/commands/` |
| Controller dispatch route | Implemented + live accepted | Realm server / ControllerService path | `.agentos/evidence/issue-64/control-inbox.json`; real Control Inbox acceptance reached ControllerService |
| Core deployment authority / generation fence | Implemented + live accepted | governed claim/install/release path, Action Relay deployment fence | `docs/CORE_DEPLOYMENT_AUTHORITY.md`, active-lease conflict proof, Issue #64 acceptance |
| Platform driver abstraction | Implemented + tested | `agent_core/platform/`, `scripts/platform_runtime.py` | `tests/test_platform_runtime.py` |
| Governance drift guard | Implemented + tested | `scripts/drift_guard.py`, constitution/role registries | `tests/test_drift_guard.py` |
| Protected-branch authority guard | Implemented | `.agent/governance/protected_branches.yaml`, `scripts/protected_branch_authority.py` | `tests/test_protected_branch_authority.py`, `docs/governance/decisions/GOV-2026-08-27-001-protected-branch-authority.md` |
| Evidence-first operational acceptance | Implemented | `.agentos/evidence/` | live acceptance files committed by workflows |
| Documentation Reality Guard | Implemented | `scripts/documentation_reality_guard.py` | `.github/workflows/documentation-reality-guard.yml`, `tests/test_documentation_reality_guard.py` |
| Model2IR standalone Character IR library | Implemented + tested | `libs/model2ir/` | Model2IR unit/regression workflows including reversible GLB/VRM, VRM topology, teacher dataset, weak-structure profile and isolated package install |
| Model2IR Lab GLB/VRM workbench | Implemented candidate; live deployment pending explicit authority | `scripts/model2ir_lab_server.py`, `scripts/deploy_model2ir_lab.py`, `web_assets/model2ir-lab.html` | `tests/test_model2ir_lab.py`, `Model2IR Lab v0.1`; Oracle release is manual-dispatch only and public acceptance does not exist until an authorized release succeeds |
| Model-independent Cognitive IR | Research | operational handoff envelopes exist, but general sufficiency is not canonical | requires repeatable cross-model continuity benchmark |
| Zero-cost model switch with only `continue` | Target / not yet proven generally | depends on portable working-state + canonical resolution layer | continuity benchmark still required |

## Canonical Project Identity contract

Project identity is explicitly separated from repository, checkout path, runtime path, deployment target, and state storage.

The canonical project document uses schema `agentos.project/v1` and includes at minimum `project_id`, `display_name`, aliases, source repository/branch/path/node, and state locations. `project_id` is a stable logical identity and must not be derived from a repository name or checkout directory.

## Project release-lane authority

Project identity alone does not authorize a branch mutation or deployment. AgentOS Core models project development, promotion, POC deployment, and production deployment as separate authorities.

For LayoutLib the canonical contract is:

```text
active development: alston-personal/layoutlib/develop or explicit feature/fix/governance branch
promotion state:    alston-personal/layoutlib/main
POC surface:        https://studio.milkcat.org/poc/layout-lab/
POC source:         validated, pinned develop candidate
production surface: https://studio.milkcat.org/layout-lab/
production source:  promoted main/release state
immutable baseline: release/v0.7.9
promotion/deploy authority: AgentOS Core
```

A project-development action targeting LayoutLib `main` is denied. Promotion to `main` is a distinct action requiring an explicit human approval event plus Core governance. A passing test, a mergeable PR, a deployment capability, or the user's generic `continue` instruction is not promotion approval.

Project threads may create project commits, tests, evidence, and candidate requests on the development lane. They must not acquire deployment authority by directly editing `agentmanager` deployment workflows. POC deployment consumes a validated candidate commit selected from the registered development branch; production consumes only promoted state. These rules are machine-readable in `.agent/governance/project_release_lanes.yaml` and enforced by `scripts/check_project_release_lane.py`.

For LayoutLib POC deployment, Core additionally requires an exact 40-character `candidate_sha`. The deployment workflow first authorizes `poc_deploy` against `develop`, clones the explicit `develop` branch, verifies the candidate is an ancestor of that branch, checks out the candidate in detached mode, and records both `layoutlib-source-branch=develop` and the exact candidate commit in the public POC document. The release-lane CI guard checks this workflow contract so it cannot silently regress to cloning the repository default branch.

This contract was introduced after the LayoutLib v0.8 development incident in which project development landed directly on project `main` and the project thread then attempted to own Core deployment orchestration. Existing history is not rewritten; the correction establishes the authority boundary from this point forward.

## Realm Node Map and capability semantics

The Realm Node Map is persistent ONE-side state. A node record may include heartbeat freshness, reported/effective status, capabilities, tool presence, and surface inventory.

Important distinctions:

- a conceptual/logical surface is not automatically an enrolled live node;
- a capability advertised by a node is not authority to execute it;
- transport reachability is not the same as capability availability;
- reaching ControllerService and receiving a node-level capability error proves the Core dispatch route is alive even though the target node is not yet ready for that action.

The authoritative live node count/status comes from the runtime NodeRegistry, not from architecture diagrams or conversation assumptions.

## Core runtime authority status

Realm Fabric is a single live Core service governed by canonical deployment state in `/home/ubuntu/agent-data/governance/core-deployment.json`. The deployment state tracks desired/observed commit, monotonic generation, lease owner/expiry, and deployment status. A live generation is converged only when desired and observed commits match and status is `converged`.

A deployment claim and an installation are separate operations. Installation cannot silently advance generation. While a deployment lease is active, another generation advance is rejected even for the same owner; the current generation must first be released/expired according to the deployment contract.

## Model2IR library and Lab boundary

Model2IR v0.9.1 is an installable Python package boundary under `libs/model2ir`. It imports GLB/glTF/VRM evidence, preserves unknown/unresolved facts, fuses explicit VRM/topology/scene evidence conservatively, audits repeatability, supports byte-preserving reversible GLB/VRM Canonical Character IR carriage, and profiles weak or relief-like geometry without inventing humanoid structure.

Model2IR Lab v0.1 is a workbench candidate around that real library, not a second inference implementation. Its browser uses Three.js only to display the uploaded model. The localhost Python service performs `extract_ir`, geometry profiling, `stabilize_external_ir`, and a three-run `audit_asset`; external stabilization remains a candidate unless explicit embedded canonical IR is recovered. Uploaded bytes are scoped to a temporary directory and are not retained after analysis.

The v0.1 Lab accepts only a single self-contained GLB 2.0 or VRM-in-GLB container up to 32 MiB. Multi-file `.gltf + .bin + textures` bundle fidelity is explicitly **not implemented** and remains a Model2IR v0.10 gap. The Oracle release workflow is `workflow_dispatch` only: merging code and authorizing live deployment are intentionally separate authority events.

## Important invariants

### Newer user intent must never be rolled back

Compaction, replay, stale tool results, or executor switching must not replace a newer goal/correction with an older one.

### Evidence is not intent

Tool results and execution evidence can inform decisions, but they do not silently rewrite the user's active goal.

### Capability does not imply authority

The presence of a mutation tool, a mergeable pull request, a node capability, or passing CI does not itself authorize mutation. Protected-branch, Core-deployment, project-source, project-release-lane, and effect-level authority remain separate checks.

### Discover before invent

Reusable/cross-project work should resolve existing responsibility, project identity, node capability, resources, and release lane before creating parallel implementations.

### Models are executors, not the durable source of truth

AgentOS does not assume access to model activations or model-specific internal state. Durable coordination and continuity state must remain external and transportable.

### Receipts are first-class evidence

A successful process start, health endpoint, or workflow status is not enough to claim end-to-end correctness. Architecture-sensitive acceptance should preserve capability/action receipts and, when relevant, real transport-path evidence under `.agentos/evidence/`.

## Memory and Cognitive IR boundary

Historical three-layer memory remains a useful conceptual model: L1 immediate/working state, L2 project/continuation state, and L3 stable cross-project knowledge and learned patterns. Current AgentOS separates canonical project state, continuation/work state, governance state, runtime state, receipts/evidence, and validated knowledge.

Model-independent Cognitive IR remains a research hypothesis until repeatable cross-model continuity benchmarks demonstrate preservation of active goal, decisions/constraints, rejected paths, open questions, and next direction.

## Deprecated / historical paths

Historical or compatibility surfaces must not be described as current canonical architecture by themselves, including pulse files/brain dumps as canonical state, repository name as Project Identity, direct GitHub rediscovery as the normal continuation path, process health alone as deployment proof, installer-side implicit generation advance, and project threads directly owning Core deployment orchestration.

## Documentation ownership rule

`README.md`, `ONBOARDING.md`, `AGENTS.md`, `docs/CURRENT_STATE.md`, and `docs/CORE_CONTROL_ROOM.md` are authoritative entry points. Architecture-sensitive implementation changes must update at least one appropriate canonical document in the same change set.

When implementation contradicts this file, fix the file immediately; do not preserve an obsolete narrative for continuity's sake.
