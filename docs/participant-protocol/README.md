# AgentOS Participant Protocol

Status: draft canonical replacement model for Node/Executor/Agent onboarding.

## Goal

Any new Node, Executor, Agent, model, browser surface, service, device, worker or future component SHOULD be able to join AgentOS ONE by reading this protocol, implementing the thinnest adapter, proving conformance, and enrolling without requiring product-specific changes in ONE Core.

The generic term is **Participant**.

A Participant MAY hold multiple roles. Scheduling MUST be based on verified capabilities/features, not product names, hostnames, runner labels, OS names, or provider-specific branches.

## Invariants

1. ONE Core MUST NOT require a product-specific code path to add a new Participant.
2. Product differences belong in adapters.
3. A claimed capability is not a verified capability.
4. Install != enroll != verify != register != READY.
5. Protocol evolution MUST NOT implicitly invalidate an existing Participant.
6. Old and new protocol versions MAY coexist.
7. Scheduler decisions MUST use verified capability + required feature + policy + availability.
8. Important execution MUST produce receipts/evidence.
9. Participant state MUST be reconcilable from desired vs observed state.
10. Runtime negotiation is authoritative; adapter version alone MUST NOT imply method support.

## Roles

Examples only; roles are not mutually exclusive:

- node
- executor
- executor-host
- agent
- model-provider
- browser-surface
- gui-surface
- service
- device
- human

A Participant describes both:

- capabilities it **provides**
- capabilities it **consumes**

## Protocol versioning

Participant protocol and adapter software version are independent.

Example:

```yaml
adapter:
  name: agentos-windows-adapter
  version: 3.4.2

protocol:
  name: agentos-participant
  supported: ["1.0"]
```

ONE and the Participant MUST negotiate the highest mutually supported protocol version.

Example:

```text
ONE supports       1.0, 1.1
VOPC5750 supports  1.0
=> negotiated 1.0

NewNode supports   1.0, 1.1
=> negotiated 1.1
```

A Participant on 1.0 remains operational when ONE adds 1.1. It simply does not expose 1.1-only methods/features.

### Version rules

Protocol versions use MAJOR.MINOR.

Minor releases MAY add:

- optional methods
- optional fields
- optional feature advertisements
- optional receipt metadata
- compatible negotiation behavior

Minor releases MUST NOT invalidate a conforming Participant from an earlier release of the same major version.

Major releases MAY change incompatible semantics, remove methods, alter wire format or enrollment semantics.

ONE SHOULD support more than one major/minor version during migration windows.

## Method advertisement

Negotiated protocol version is not enough. A Participant MUST explicitly advertise methods and their runtime status.

Example:

```yaml
methods:
  describe:
    implemented: true
    available: true
    verified: true
  cancel:
    implemented: false
    available: false
    verified: false
```

ONE MUST NOT assume a method is usable because of adapter version, source-code presence, intended role, or protocol version alone.

## Method lifecycle

A protocol method definition declares:

- since
- required | optional | deprecated | removed
- request schema
- response schema
- failure semantics

Participant runtime advertisement declares:

- implemented
- available
- verified
- unavailable_reason, when applicable

## Capability versioning

Capability contracts are versioned independently from Participant Protocol.

Example:

```yaml
protocol:
  negotiated: "1.1"

capabilities:
  browser.interact:
    supported_versions: ["1"]
  shell.execute:
    supported_versions: ["1", "2"]
```

Participant Protocol answers: **how do you speak to ONE?**

Capability Contract answers: **what does this capability mean?**

## Feature advertisement

Work SHOULD request semantic features rather than transport/RPC implementation details.

Example:

```yaml
features:
  task.cancel:
    available: true
    verified: true
  task.resume:
    available: false
    verified: false
```

Scheduler resolution:

```text
Work requirements
 -> capability + feature constraints
 -> verified Participant candidates
 -> policy / lease / priority / load
 -> execution
```

## Minimum lifecycle

```text
DISCOVER
 -> BOOTSTRAP
 -> INSPECT
 -> ADAPT
 -> MANIFEST
 -> ENROLL
 -> NEGOTIATE
 -> CONFORMANCE
 -> REGISTER
 -> READY
```

Possible runtime states:

- DISCOVERED
- BOOTSTRAPPING
- INSPECTING
- ADAPTING
- ENROLLING
- VERIFYING
- READY
- DEGRADED
- BLOCKED
- QUARANTINED
- OFFLINE
- REVOKED

## Self-reconciliation

Participants SHOULD implement:

```text
observe -> compare -> plan -> apply -> verify
```

Requirements MUST distinguish at least:

- SATISFIED
- INSTALLABLE
- HUMAN_REQUIRED
- POLICY_DENIED
- UNSUPPORTED
- FAILED

A missing dependency MUST NOT be represented as an unexplained crash.

## Enrollment

Enrollment submits:

- stable Participant identity
- manifest
- requested realm
- identity proof/attestation
- requested permissions
- dependency/host relationships

ONE returns an explicit state such as:

- APPROVED
- PENDING
- CHALLENGE
- REJECTED

Only after negotiation and conformance MAY a Participant become READY.

## Conformance

All Participants run Core Conformance.

Capability-specific suites are added for each claimed capability.

Process-running or HTTP-200 alone is not PASS.

Core conformance SHOULD cover:

- identity
- protocol negotiation
- describe
- probe
- health
- failure semantics
- timeout
- receipt
- reconnect

Where supported by negotiated protocol/features it SHOULD additionally cover:

- cancel
- resume
- streaming
- artifact transfer

## Receipt rule

Important work must make provenance recoverable:

```yaml
receipt:
  id:
  work_id:
  task_id:
  requested_by:
  authorized_by:
  executed_by:
  participant:
  adapter:
  protocol:
  capability:
  feature_set:
  started_at:
  finished_at:
  status:
  inputs_digest:
  outputs:
  artifacts:
  evidence:
  error:
```

## Host/dependency graph

Participants MAY host or depend on other Participants.

Example:

```text
participant://agent/gemini-web
    depends_on -> participant://surface/chromium-session
    hosted_by  -> participant://node/vopc5750
```

ONE SHOULD derive availability through this graph rather than reporting unrelated downstream failures.

## Work ownership

Work, IR, artifacts and receipts belong to ONE/work identity, not to an LLM/browser session.

Participants are execution/decision participants in that Work.

## Adapter rule

An adapter is the thinnest mapping from a native interface to AgentOS contracts.

Adapters MUST NOT:

- modify ONE Core merely to accommodate a product
- bypass enrollment
- self-mark claimed capabilities as verified
- bypass policy/effect authorization
- forge receipts
- hard-code runner/host routing when capability routing is available

## Legacy mapping

Existing concepts map as follows:

- Oracle / VOPC5750 / dqa03 -> Participant with node/executor-host roles
- GitHub self-hosted runner -> Participant/executor adapter, not the scheduler authority
- GUI Worker -> Participant providing GUI/browser capabilities
- Gemini / ChatGPT / Claude / Codex -> Participants providing/consuming agent/model capabilities

Existing AgentOS Node and Executor contracts remain valid evidence/legacy behavior until migrated. New Participant Protocol must preserve established authority boundaries, especially:

```text
advertised != routable != authorized != successfully executed
```

## Canonical implementation directory

This directory is versioned.

- `v1.0/` contains the current initial contract.
- Future compatible additions go to `v1.1/`, `v1.2/`, etc.
- Existing Participants remain on their negotiated version until their adapters are upgraded and re-verified.

See:

- `v1.0/CONTRACT.md`
- `v1.0/participant.schema.json`
- `CONFORMANCE.md`
- `GEMINI_WEB_ONBOARDING.md`
