# AgentOS Participant Self-Onboarding

This is the single canonical onboarding entrypoint for any new AgentOS Participant.

A Participant may be a Node, Executor, Agent, model provider, browser/GUI surface, service, device, worker, human-facing bridge, or future component type.

Do not create product-specific onboarding flows. Product/platform differences belong in adapters and examples.

## Authoritative references

Read these before implementation:

1. ../README.md
2. ../v1.0/CONTRACT.md
3. ../v1.0/participant.schema.json
4. ../CONFORMANCE.md
5. ../ACCEPTANCE.md

## Objective

Join AgentOS ONE by implementing or selecting the thinnest adapter that maps your native interfaces onto the existing AgentOS Participant Protocol.

If your environment cannot maintain its own persistent transport, you MAY join as a **hosted Participant**. In that case, a trusted AgentOS host/bridge (for example a GUI Worker, browser bridge, node daemon, API bridge, or CLI host) owns the persistent transport and invokes your native surface on your behalf.

Do not modify ONE Core merely to accommodate your product or runtime.

## Required workflow

```text
identify self
-> inspect native interfaces/runtime
-> discover ONE
-> read supported protocol versions
-> select or build adapter
-> produce Participant Manifest
-> validate manifest schema
-> declare provided/consumed capabilities
-> declare requirements/blockers
-> request enrollment
-> negotiate protocol
-> run Core Conformance
-> run capability-specific conformance
-> perform ONE-routed end-to-end invocation
-> emit acceptance receipt
-> report exact A0-A7 acceptance level
```

## Runtime modes

A Participant MAY use either:

### Direct mode

The Participant runtime can directly maintain the required transport/session to ONE.

### Hosted mode

Use this when the Participant is a Web/chat surface or other constrained runtime that cannot itself maintain persistent sockets, daemons, polling loops, credentials, or filesystem state.

In hosted mode:

- the Participant identity is still distinct from the host/bridge identity
- the host/bridge owns transport, session persistence, retries, leases, and execution plumbing
- the Participant supplies the cognitive/native capability
- the manifest MUST declare `hosted_by` and any `depends_on` relationships
- ONE verifies the end-to-end path through the host/bridge
- a Web model must NOT be rejected merely because it cannot itself run a daemon or WebSocket client

Example:

```text
participant://agent/gemini-web
  hosted_by  -> participant://node/vopc5750
  depends_on -> participant://surface/chromium-session
```

## Adapter rules

The adapter MUST map native interfaces to existing AgentOS methods/capabilities, remain thin, keep adapter and protocol versions separate, advertise only actually implemented functions, surface blockers explicitly, preserve stable Participant identity, and emit evidence/receipts.

It MUST NOT add product-specific logic to ONE Core, bypass enrollment, self-verify capabilities, hard-code runner/node routing where capability routing exists, silently approximate unsupported methods, or hide HUMAN_REQUIRED / POLICY_DENIED / timeout / transport / dependency failures.

## Protocol negotiation

Advertise all supported Participant Protocol versions. ONE selects the highest mutually supported version. An older Participant may continue using an older negotiated version and simply lack newer methods/features.

## Runtime advertisement

Methods/features report:
- implemented
- available
- verified
- unavailable_reason when applicable

Capabilities report:
- supported_versions
- available
- verified
- unavailable_reason when applicable

Only ONE-side verification makes a capability scheduler-eligible.

## Requirements and blockers

Use explicit states including:
- SATISFIED
- INSTALLABLE
- HUMAN_REQUIRED
- POLICY_DENIED
- UNSUPPORTED
- FAILED

Do not hang indefinitely on login, MFA, approval, administrator permission, physical action, unavailable dependency, or missing ONE runtime surface.

## Acceptance

Use ../ACCEPTANCE.md exactly.

Do not say "joined", "connected" or "ready" unless A7 READY is proven.

If blocked, report the highest level reached, for example:

```text
A0 PASS
A1 PASS
A2 PASS
A3 PASS
A4 PASS
A5 BLOCKED
reason: HUMAN_REQUIRED / LOGIN_REQUIRED
```

## Required completion report

Return:
1. Participant identity and roles
2. adapter path/name/version
3. final Participant Manifest
4. supported + negotiated protocol versions
5. implemented/available/verified methods
6. claimed + verified capabilities
7. available/verified features
8. requirements and blockers
9. host/dependency relationships
10. Core Conformance result
11. capability-specific conformance result
12. A0-A7 Acceptance Report
13. enrollment/execution/acceptance receipt IDs
14. generic protocol/runtime gaps discovered in ONE

If a generic ONE surface required by the contract is missing, report the platform gap. Do not create a product-specific exception.

## Definition of success

```text
enrolled
AND negotiated
AND conformant
AND at least one required capability verified
AND one ONE-routed end-to-end invocation proven
AND correlated receipt preserved
AND registry state READY
```

Anything less must be reported as the exact partial acceptance level.
