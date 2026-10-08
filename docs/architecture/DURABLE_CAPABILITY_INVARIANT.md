# Durable Capability Invariant (DCI) — Candidate v0.1

Status: **proposed / not live accepted**. Tracking: [#1672](https://github.com/alston-personal/agentmanager/issues/1672).

## Rule
An AgentOS capability is a versioned, discoverable system contract **independent of any LLM conversation or model memory**. A model may be invoked as a bounded, replaceable decision provider *inside* an authorized execution, but MUST NOT be the sole trigger, persistent queue, state holder, executor discovery method, or recovery mechanism.

Do not confuse a capability's registration, transport reachability, authorization, readiness, and observed successful execution.

## Canonical ownership (reuse before build)
- Capability definitions and governance: existing Governance Directory / manifest adapter / capability resolution gate.
- Durable assignment, lease, checkpoints, idempotency, outcomes: existing Control Plane and completion ledger.
- Scheduler/Supervisor: existing [#200](https://github.com/alston-personal/agentmanager/issues/200), not one timer per capability or role.
- Execution: governed ONE transport -> Node -> registered Executor; capability != authority.
- Proof: node-authoritative typed receipts and sanitized evidence in data layer; do not infer runtime truth from CI or chat claims.
- Runtime isolation and rollback: existing [#470](https://github.com/alston-personal/agentmanager/issues/470).

## Minimal manifest fields (map to existing schemas first)
`id`, `version`, `input_schema`, `output_schema`, `entrypoint`, `owner`, `required_capabilities`, `authorization_scope`, `timeout`, `idempotency_policy`, `probe`, `receipt_validator`, `recovery_policy`, `compatibility`.

Do not introduce a second registry if current manifest schemas already support any of these.

## Runtime truth / state
Distinguish **REGISTERED / ROUTABLE / AUTHORIZED / READY** from **EXECUTING / VERIFIED** and **DEGRADED / BLOCKED / RECOVERING / WAITING_PROVIDER**. These are semantic classes, not a mandate to duplicate current state enums. Historical PASS and mere QUEUED are not live VERIFIED.

## Loss/recovery rules
- Model/session disappears: durable work persists; machine trigger or Supervisor finds eligible assignments independently.
- Provider unavailable: record WAITING_PROVIDER, bounded retry or permitted fallback; don't lose intent.
- Executor restart / network break: lease expiry plus persisted checkpoint; reconcile external side effects as UNKNOWN before retry when idempotence is not proven.
- Deployment: inactive-generation end-to-end probes; block promotion/rollback for regression; pin exact runtime generation.
- Human authority remains mandatory for protected changes, credentials, legal attestation, purchases, and final external submission.

## First vertical slice and acceptance
Use [#1667](https://github.com/alston-personal/agentmanager/issues/1667) as a consumer, not the architecture owner.
1. Machine-trigger a scoped authorized `desktop.open_url` through ONE to an actual GUI Executor.
2. Collect screenshot/readback + **terminal** node-authoritative receipt with runtime generation, executor identity and timestamps.
3. Repeat after a fresh chat/session, model-provider swap and executor restart without reconstructing the workflow through the model's memory.
4. Repeat after a production upgrade; a regression must be detected and rolled back or blocked.
5. Demonstrate blocked/auth-required/provider-unavailable states without silent loss, false success, or unauthorized submission.

A passing unit test, existing GitHub issue, historical screenshot or queued dispatch does **not** satisfy these live acceptance criteria.

## Implementation order
Inventory existing manifest schema -> add only missing contract validation -> test deterministic execution and recovery -> live Oracle GUI transport probe -> deployment regression fence -> record receipts and close #1672 only on evidence.
