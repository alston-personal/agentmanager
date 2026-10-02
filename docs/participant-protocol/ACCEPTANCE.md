# AgentOS Participant Acceptance Specification

Acceptance is part of the protocol contract. A Participant MUST know both how to integrate and how success is proven.

## Acceptance authority

Acceptance is split into two authorities:

1. **Participant-side self-test**
   - proves the adapter believes it implements the contract.
   - NEVER grants READY or verified capability status.

2. **ONE-side acceptance**
   - authoritative.
   - verifies identity, negotiation, methods, capabilities, features, policy boundaries, execution path, and receipts.

Only ONE-side acceptance can move a Participant to READY.

## Acceptance levels

A Participant progresses through these gates:

### A0 — DISCOVERED

Evidence:
- ONE endpoint discovered
- protocol metadata reachable

Not enough for enrollment.

### A1 — ADAPTER_BUILT

Evidence:
- adapter implementation exists
- adapter version identified
- manifest generated
- manifest validates against schema

Still not enrolled.

### A2 — ENROLLED

Evidence:
- stable Participant identity accepted by ONE
- enrollment APPROVED
- realm/permissions recorded

Still not READY.

### A3 — PROTOCOL_NEGOTIATED

Evidence:
- ONE and Participant report the same negotiated protocol version
- no implicit version upgrade occurred
- required methods for that negotiated version are advertised

### A4 — CORE_CONFORMANT

Evidence:
- all required protocol methods pass
- error semantics pass
- timeout behavior passes
- health is observable
- receipt path passes
- reconnect preserves stable identity

### A5 — CAPABILITY_VERIFIED

For every claimed capability that should become scheduler-eligible:

- capability version is negotiated/supported
- capability-specific conformance passes
- required features pass
- ONE marks the capability verified

Unverified capabilities MUST remain visible as claimed/unavailable but MUST NOT be scheduled.

### A6 — END_TO_END_ACCEPTED

At least one real task MUST pass through:

```text
requester
 -> ONE
 -> scheduler
 -> selected Participant
 -> adapter
 -> native implementation
 -> adapter response
 -> ONE
 -> correlated receipt/evidence
```

The test MUST verify that ONE selected the Participant because of capability/feature matching, not because of a hard-coded hostname, runner, provider or product branch.

### A7 — READY

A Participant may become READY only after A0-A6 pass for the minimum acceptance profile required by its role/capabilities.

## Negative acceptance tests

Acceptance MUST prove correct rejection, not only successful execution.

At minimum test:

- unsupported method -> UNSUPPORTED_METHOD
- unsupported capability -> UNSUPPORTED_CAPABILITY
- unverified capability -> CAPABILITY_NOT_VERIFIED
- missing human login/approval -> HUMAN_REQUIRED
- policy denial -> POLICY_DENIED
- timeout -> TIMEOUT
- lost transport -> TRANSPORT_ERROR
- dependency unavailable -> REQUIREMENT_BLOCKED or equivalent explicit status

Silent fallback is a failure.

## Version compatibility acceptance

Every protocol release MUST include coexistence tests.

Example for v1.1:

```text
ONE supports 1.0 + 1.1
VOPC5750 supports 1.0
NewNode supports 1.1
```

Acceptance must prove:

- VOPC5750 still reaches READY on 1.0
- NewNode reaches READY on 1.1
- v1.0 work may schedule to either when capabilities match
- work requiring a v1.1-only feature excludes VOPC5750
- ONE never calls a v1.1-only method on VOPC5750
- VOPC5750 is not forced offline merely because 1.1 exists

## Upgrade acceptance

When an existing Participant upgrades its adapter:

```text
same stable Participant identity
 -> advertise new supported protocol version
 -> negotiate
 -> verify only newly introduced methods/features/capability versions
 -> atomically update registry after PASS
```

Failure of the upgrade MUST NOT erase the last known valid protocol/capability state unless the old implementation is actually unavailable.

## Role acceptance profiles

### Node / executor-host

Must additionally prove:

- heartbeat freshness
- hosted Participant/dependency relationships
- at least one provided execution capability if it claims executor-host functionality
- offline/degraded propagation behaves correctly

### Executor

Must additionally prove:

- capability invocation
- failure/timeout reporting
- receipt generation
- cancellation/resume only when advertised

### Agent / model-provider

Must additionally prove:

- ONE can invoke at least one reasoning/review capability
- response returns through ONE
- session/transport identity is not confused with Participant identity
- result is correlated with work/task identity

### GUI/browser surface

Must additionally prove:

- session availability is observable
- session lock/lease behavior if required
- GUI/login blockers surface explicitly
- artifacts/evidence can be correlated to the task

## Acceptance receipt

Final acceptance SHOULD emit one canonical receipt:

```yaml
schema: agentos.participant-acceptance/v1
participant_id:
adapter:
  name:
  version:
protocol:
  supported: []
  negotiated:
acceptance:
  a0_discovered: PASS
  a1_adapter_built: PASS
  a2_enrolled: PASS
  a3_protocol_negotiated: PASS
  a4_core_conformant: PASS
  a5_capability_verified: PASS
  a6_end_to_end_accepted: PASS
  a7_ready: PASS
verified_methods: []
verified_capabilities: []
verified_features: []
limitations: []
evidence: []
status: PASS
```

## Definition of Done

The phrase "joined AgentOS" MUST mean:

```text
enrolled
AND negotiated
AND conformant
AND at least one required capability verified
AND one end-to-end invocation proven
AND receipt preserved
AND registry state READY
```

Anything less must be reported with its exact highest acceptance level, for example:

- A1 ADAPTER_BUILT
- A3 PROTOCOL_NEGOTIATED
- A4 CORE_CONFORMANT
- BLOCKED at A5: LOGIN_REQUIRED

This prevents "process is running", "HTTP 200", "browser prompt succeeded", or "manifest exists" from being mistaken for successful integration.
