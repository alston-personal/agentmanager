# AgentOS Core Deployment Authority

Status: implementation contract  
Status date: 2026-08-28

## Problem

Realm Fabric is a single live Core service, but more than one governed workflow/agent may be capable of requesting Core deployment actions.

A capability being authorized to request a deploy does **not** mean it may unconditionally replace the currently desired Core generation.

Without an authority fence, two individually valid deployments degrade into last-writer-wins behavior. That violates AgentOS governance because a delayed or concurrent workflow can silently invalidate the active generation relied on by another node/session.

## Invariant

> Capability does not imply deployment authority.

The live Realm Fabric generation may change only through the canonical deployment state machine.

Canonical state fields include:

- `desired_core_commit`
- `observed_core_commit`
- `deployment_generation`
- `lease_owner`
- `lease_expires_at`
- `deployment_status`

A deployment is converged only when:

```text
desired_core_commit == observed_core_commit
deployment_status == converged
```

## Canonical state

Runtime state:

```text
/home/ubuntu/agent-data/governance/core-deployment.json
```

Schema:

```text
agentos.core-deployment/v1
```

Generation is monotonically increasing. It is never inferred from Git history, process age, workflow run number, PID, filesystem timestamps, or a health endpoint.

## Claim / Compare-and-Swap

A writer must claim the next generation before installation.

Conceptual action:

```text
agentos.realm-fabric.claim_deployment
```

with:

```text
desired_core_commit
lease_owner
expected_generation
lease_seconds
```

Current rule:

1. `expected_generation` must equal the canonical current generation.
2. The current generation must be releasable; an unexpired active lease blocks generation advance.
3. **The active-lease block applies even when the new request uses the same `lease_owner`.**
4. Only after the prior generation is released/expired may a successful claim atomically advance `deployment_generation` and establish the new desired commit + lease.

This same-owner rule is intentional. A delayed retry, duplicated workflow, or independently legitimate workflow using the same logical owner must not be able to steal the active generation by presenting the same owner string.

If competing writers race from the same prior generation, at most one valid transition may succeed.

## Claim, install, and release are separate operations

The installer is not allowed to invent or advance a generation.

The canonical transition is:

```text
claim next generation
    -> install exact claimed release
    -> attest observed release
    -> converge
    -> release / end lease when transition ownership is complete
```

A request that needs a newer generation while the current lease is active must first follow the release/expiry contract. This prevents installer-side implicit transitions and closes the race exposed during the Node Golden Path work.

## Install Fence

`agentos.realm-fabric.install_release` must include the fenced identity of the claimed deployment, including:

```text
source_commit
desired_core_commit
lease_owner
deployment_generation
```

Before any service unit rewrite or restart, the Action Relay verifies under the deployment lock that:

- `source_commit == desired_core_commit`
- canonical `desired_core_commit == source_commit`
- canonical `deployment_generation == request.deployment_generation`
- canonical `lease_owner == request.lease_owner`
- the lease is still active for the claimed generation

Any mismatch returns a rejected deployment receipt and must not mutate the live service.

Legacy callers that send only `source_commit` are intentionally rejected.

## Observed Generation

The observed Core commit is derived from the exact release referenced by the live Realm Fabric service, not from `/home/ubuntu/agentmanager` HEAD.

This preserves the invariant:

```text
canonical source checkout != deployed runtime generation
```

A canonical checkout may move ahead while the currently deployed generation remains deliberately pinned.

## Deployment Receipt

A successful deployment receipt must expose enough information to prove the intended generation, at minimum:

```text
desired_core_commit
observed_core_commit
deployment_generation
lease_owner
lease_expires_at
deployment_status=converged
```

The Action Relay owns the outer receipt schema `agentos.action-receipt/v1`. Capability-specific result schemas may not overwrite reserved receipt-envelope fields.

A rejection receipt is also evidence. A governance rejection must remain visible and must not be rewritten into a generic transport failure.

## Rejection States

Expected governed rejections include:

- `rejected_lease`
- `rejected_generation`
- `rejected_desired_mismatch`
- `rejected_fence`

A rejected request is a governance outcome, not a transport failure.

## Real-path acceptance contract

Core stability is not established by `/health`, PID survival, or successful installation alone.

When the deployed Core is expected to support a controller path, acceptance should test the real transport boundary. Issue #64 established the canonical example:

```text
Bootstrap Control Inbox
  -> Oracle bridge / ONE
  -> POST /v1/controller/dispatch
  -> ControllerService
```

PASS for the Core boundary means the request reaches ControllerService and does not fail with the former Core-level HTTP 404. A later node-level outcome such as `NODE_CAPABILITY_NOT_ADVERTISED` is acceptable evidence that Core routing is alive while Node readiness is incomplete.

The final Issue #64 acceptance was persisted at:

```text
.agentos/evidence/issue-64/control-inbox.json
```

## Node Golden Path Contract

Before continuing OTA / node readiness work, the Node thread may query Core deployment state and require:

```text
desired_core_commit=<authoritative desired commit>
observed_core_commit=<same commit>
deployment_generation=<positive monotonic integer>
lease_owner=<canonical deployment owner or released state per contract>
deployment_status=converged
```

The Node thread must not infer Core stability from process PID or health endpoints alone and must not mutate Core to compensate for a node-level capability convergence problem.

## Incident and correction

On 2026-08-28, a separate governed Core deployment restarted Realm Fabric while a Node Golden Path validation depended on another Core generation. Both writers were individually legitimate; the missing primitive was deployment-generation authority arbitration at the final mutation boundary.

Subsequent testing exposed a second weakness: treating the same `lease_owner` as automatically safe still allowed delayed same-owner work to advance generation. The contract was therefore tightened so an active lease blocks generation advance regardless of owner equality; release/expiry is required before transition.

This establishes two permanent rules:

1. workflow-level authorization/concurrency is insufficient; the live mutation boundary must enforce generation authority;
2. logical owner identity is not a substitute for generation ownership and lifecycle state.

## Deprecated behavior

The following are non-canonical and must not be reintroduced:

- last-writer-wins deployment;
- installer-side generation increment;
- same-owner active-lease generation stealing;
- deriving deployed generation from checkout HEAD/PID/process age;
- treating `/health` alone as end-to-end acceptance;
- legacy unfenced deploy calls containing only `source_commit`;
- masking governance rejection verdicts as generic failures.
