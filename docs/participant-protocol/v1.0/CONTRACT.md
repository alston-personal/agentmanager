# AgentOS Participant Protocol v1.0

Protocol ID: `agentos-participant/1.0`

## Required methods

A v1.0 Participant MUST implement and advertise:

- `describe`
- `probe`
- `invoke`
- `status`
- `receipt`
- `shutdown`

## Optional methods

A v1.0 Participant MAY additionally advertise extension methods. ONE MUST NOT call an extension method unless it is explicitly advertised and verified.

## describe

Returns the current Participant Manifest.

Minimum response fields:

```yaml
participant:
  id:
  instance_id:
  roles: []

adapter:
  name:
  version:

protocol:
  name: agentos-participant
  supported: ["1.0"]
  negotiated: "1.0"

methods: {}
capabilities: {}
features: {}
requirements: []
relationships: []
health: {}
receipt:
  supported: true
```

## probe

Returns current observed state and requirement status.

Probe is descriptive and MUST NOT imply authority.

## invoke

Requests execution of a verified capability.

Minimum request:

```yaml
work_id:
task_id:
capability:
capability_version:
inputs:
required_features: []
```

The adapter MUST reject unsupported/unverified capabilities rather than silently approximating them.

## status

Returns task and Participant execution status.

## receipt

Returns or emits execution provenance/evidence.

## shutdown

Requests graceful adapter shutdown where policy permits.

## Failure semantics

A v1.0 adapter MUST distinguish at least:

- UNSUPPORTED_METHOD
- UNSUPPORTED_CAPABILITY
- CAPABILITY_NOT_VERIFIED
- REQUIREMENT_BLOCKED
- AUTHORIZATION_REQUIRED
- POLICY_DENIED
- TIMEOUT
- TRANSPORT_ERROR
- EXECUTION_FAILED
- HUMAN_REQUIRED

## Protocol negotiation

Participant sends supported versions. ONE selects the highest mutually supported version.

If there is no common version, enrollment MUST remain BLOCKED and report:

```text
NO_COMMON_PROTOCOL_VERSION
```

## Compatibility

A Participant conforming to v1.0 MUST remain operable while ONE later supports compatible v1.x versions.

ONE MUST NOT call methods introduced after v1.0 unless the Participant advertises and verifies them.

Example future behavior:

```text
VOPC5750: negotiated 1.0
NewNode:   negotiated 1.1

1.1 adds task.cancel

VOPC5750:
  ordinary v1.0 work -> eligible
  work requiring task.cancel -> ineligible

NewNode:
  ordinary v1.0 work -> eligible
  work requiring task.cancel -> eligible after verification
```

## Verification rule

Runtime truth is:

```text
declared
 -> implemented
 -> available
 -> verified
```

Only `verified=true` is scheduler-eligible.

## Authority boundary

The protocol preserves the existing AgentOS distinction:

```text
advertised capability
 != routable transport
 != authorized effect
 != successful execution
```

## READY definition

A Participant is READY only when:

- identity is accepted
- enrollment is approved
- protocol negotiation succeeded
- required v1.0 methods passed conformance
- required capabilities are verified
- health is observable
- receipt path is verified
- scheduler registry has current availability
