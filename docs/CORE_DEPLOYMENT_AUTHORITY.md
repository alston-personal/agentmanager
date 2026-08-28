# AgentOS Core Deployment Authority

Status: implementation contract

## Problem

Realm Fabric is a single live Core service, but more than one governed workflow/agent may be capable of requesting `agentos.realm-fabric.install_release`.

A capability being authorized to request a deploy does **not** mean it may unconditionally replace the currently desired Core generation.

Without an authority fence, two individually valid deployments degrade into last-writer-wins behavior. That violates AgentOS governance because a later workflow can silently invalidate the active goal of another node or session.

## Invariant

> Capability does not imply deployment authority.

The live Realm Fabric generation may change only when the request satisfies the canonical deployment state.

The canonical state is represented by:

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

## State

Canonical runtime state:

```text
/home/ubuntu/agent-data/governance/core-deployment.json
```

Schema:

```text
agentos.core-deployment/v1
```

Generation is monotonically increasing. It is never inferred from Git history, process age, workflow run number, or filesystem timestamps.

## Claim / Compare-and-Swap

A writer must first call:

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

The claim is accepted only when:

1. `expected_generation` equals the current canonical generation; and
2. there is no unexpired lease owned by a different owner.

Successful claim atomically advances `deployment_generation` and records the desired commit and lease.

If another writer races using the same prior generation, only one CAS may succeed.

## Install Fence

`agentos.realm-fabric.install_release` must include:

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
- lease is still active

Any mismatch returns a rejected deployment receipt and must not mutate the live service.

Legacy callers that send only `source_commit` are intentionally rejected after the fence is deployed.

## Observed Generation

The observed Core commit is derived from the exact release referenced by the live Realm Fabric systemd `ExecStart`, not from `/home/ubuntu/agentmanager` HEAD.

This preserves the invariant:

```text
Canonical source checkout != deployed runtime generation
```

## Deployment Receipt

A successful deployment receipt must expose at minimum:

```text
desired_core_commit
observed_core_commit
deployment_generation
lease_owner
lease_expires_at
deployment_status=converged
```

The Action Relay owns the outer receipt schema `agentos.action-receipt/v1`. Capability-specific result schemas may not overwrite reserved receipt envelope fields.

## Rejection States

Expected governed rejections include:

- `rejected_lease`
- `rejected_generation`
- `rejected_desired_mismatch`
- `rejected_fence`

A rejected request is a governance outcome, not a transport failure.

## Node Golden Path Contract

Before continuing OTA / `vopc5750` Golden Path, the Node thread may query the Core deployment status and require:

```text
desired_core_commit=<expected Core commit>
observed_core_commit=<same commit>
deployment_generation=<positive monotonic integer>
lease_owner=<canonical active deployment owner>
deployment_status=converged
```

The Node thread must not infer Core stability from process PID or a successful health endpoint alone.

## Incident that established this requirement

On 2026-08-28, a separate governed Core deployment installed commit `6ea6276f6b0dc065667853dbde05e6712193b380` and restarted Realm Fabric while a Node Golden Path validation depended on a different Core generation. Both writers were individually legitimate; the missing primitive was deployment authority arbitration.

This incident establishes that workflow-level authorization/concurrency is insufficient. The final live mutation boundary itself must enforce deployment generation authority.
