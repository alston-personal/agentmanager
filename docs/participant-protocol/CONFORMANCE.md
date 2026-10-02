# AgentOS Participant Conformance

A Participant is not READY merely because an adapter process is running.

## Core suite

Every Participant MUST pass:

1. identity accepted
2. manifest schema valid
3. protocol negotiation succeeds
4. required methods advertised
5. required methods callable
6. health observable
7. unsupported method fails explicitly
8. unsupported capability fails explicitly
9. timeout semantics are explicit
10. receipt can be produced and correlated to work/task identity
11. reconnect does not silently create a different stable Participant identity

## Scheduler eligibility

For a task requiring capability C, version V, and feature set F:

```text
participant enrolled
AND participant READY
AND C is advertised
AND V is supported
AND C is verified
AND every required feature in F is available + verified
AND policy permits the effect
AND required dependencies are available
```

Anything else is ineligible.

## Version coexistence test

The conformance suite MUST preserve the following case:

```text
ONE supports 1.0 + 1.1
Old participant negotiates 1.0
New participant negotiates 1.1

Result:
- both remain registered
- old participant receives only 1.0-compatible work
- 1.1 feature-dependent work excludes old participant
- no implicit forced upgrade occurs
```

## Upgrade test

When an existing adapter adds support for a newer protocol:

1. reconnect/re-enroll using the same stable Participant identity
2. advertise the additional supported protocol version
3. negotiate the highest common version
4. rerun conformance for newly introduced methods/features
5. keep new functionality unavailable until verification passes
6. update registry atomically after PASS
7. preserve previous receipts and identity history

## Failure evidence

A failed test MUST record:

- participant identity
- adapter version
- supported/negotiated protocol
- test name
- expected behavior
- observed behavior
- blocker classification
- evidence/artifact reference

## Human action

If login, MFA, physical interaction, approval or privileged permission is required, conformance MUST return HUMAN_REQUIRED rather than hang indefinitely.

## PASS receipt

A successful enrollment/conformance receipt SHOULD include:

```yaml
participant_id:
adapter_version:
protocol_supported:
protocol_negotiated:
required_methods_verified:
capabilities_verified:
features_verified:
limitations:
status: PASS
```
