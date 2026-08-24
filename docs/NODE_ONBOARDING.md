# AgentOS Node Onboarding

## Product invariant

> **The human should establish trust once; AgentOS should do the rest.**

Joining a Node must be simpler than configuring the Node manually. Preferred UX:

- scan one QR code and confirm;
- open one Join Link and confirm;
- run one short command on a server;
- zero-touch enrollment for a pre-managed fleet.

QR, URL, NFC and CLI are representations of one protocol rather than separate enrollment mechanisms.

## One-touch transport

The preferred user-facing artifact is `agentos.join-reference/v1`, not the full policy envelope. It contains only:

```text
trusted Core origin
one-time enrollment id
one-time enrollment secret
```

For a link, the reference is placed after `#`:

```text
https://core.example/join#AGENTOSREF1...
```

A normal HTTPS GET does not transmit the fragment to the web server or access logs. The bootstrap client explicitly submits it to the trusted Core origin. Core stores only the SHA-256 digest of the secret.

Core resolves the reference to its authoritative `agentos.join/v1` policy, yielding an in-memory `agentos.join-ticket/v1`. The ticket is consumed exactly once by the claim operation.

Join material MUST NOT be:

- written to durable Node state;
- included in logs, telemetry or GitHub artifacts;
- reused after a successful claim;
- accepted after expiry;
- transported to a non-HTTPS Core, except `127.0.0.1` development.

A CLI bearer reference should preferably be read from stdin or a hidden interactive prompt rather than placed directly in process arguments/shell history. `agentos-node enroll --reference-stdin` is the explicit non-interactive form; bare `agentos-node enroll` accepts a hidden prompt. `--reference` remains a development/backward-compatible escape hatch.

Bootstrap authority is deliberately tiny. It may establish identity, heartbeat, capability metadata and reconciliation metadata. It may not grant external effects.

## Lifecycle

```text
UNSEEN
  ↓ human establishes trust once
BOOTSTRAPPED
  ↓ Node identity/key established
IDENTIFIED
  ↓ metadata-only capability scan
DISCOVERED
  ↓ local cognition descriptors reconciled
RECONCILED
  ↓ Node + manifests registered
REGISTERED
  ↓ every capability resolved through GovernanceRegistry
GOVERNED
  ↓ only then
ACTIVE
  ↕ reconnect/re-discover
OFFLINE

Any stage → REVOKED
```

`REGISTERED → ACTIVE` is invalid. A Node cannot skip governance.

## Standard onboarding flow

```text
Create invitation
↓
Join Reference
↓ QR / link / CLI / NFC
Bootstrap client
↓ HTTPS resolve against trusted Core
Authoritative Join Ticket
↓
Claim once with device public key + fingerprint
↓
Stable Node Identity
↓
Capability Discovery
↓
agentos.node-capability-manifest/v1
↓
Local cognition descriptor scan
↓
agentos.node-reconciliation/v1
↓
Durable Node Directory
↓
Governance gap assessment
↓
owner/governance registration where required
↓
ACTIVE
```

## Canonical API surface

Transport implementations should route through one protocol contract instead of re-implementing onboarding semantics:

```text
POST /v1/nodes/enrollment/resolve
POST /v1/nodes/enrollment/claim
GET  /v1/nodes
GET  /v1/nodes/{node_id}
GET  /v1/nodes/{node_id}/capabilities
GET  /v1/capabilities/{capability}/nodes
```

`agent_core.node_http_api.NodeHttpApi` is the reference route contract. It is not itself a production network server: TLS termination, client authentication, rate limiting and external exposure remain responsibilities of the trusted transport adapter.

## Capability discovery

Discovery is metadata-only. It may detect things such as:

```text
repo.read
container.runtime.observe
http.client.observe
camera.observe
microphone.observe
printer.observe
usb.observe
bluetooth.observe
media.transform
browser.observe
model.provider
```

But:

> **Discovered ≠ Registered ≠ Authorized ≠ Active**

A discovered camera does not authorize capture. A discovered microphone does not authorize recording. A discovered printer does not authorize printing. A newly inserted USB device produces a capability delta; it does not silently create authority.

## Reconnect and capability deltas

A returning Node keeps its stable identity. On reconnect AgentOS re-runs discovery and compares the new manifest with the previous content-addressed manifest.

```text
+ camera.observe
- printer.observe
~ model.provider metadata changed
```

This produces `agentos.node-capability-delta/v1`. New capabilities return through governance before activation.

## Cognitive reconciliation (回歸一)

Joining a Node does not centralize all local data. AgentOS first handles metadata/provenance descriptors and classifies local cognition:

```text
already known        → link_existing
new supported claim  → candidate_promotion
contradiction        → contradiction_review
newer claim          → supersession_review
node-local material  → keep_node_local
credential/sensitive → block_sensitive
```

Raw credentials, browser profiles and explicitly sensitive local material do not cross the reconciliation transport.

## Hardware and software use the same protocol

A Node is any governed execution body that exposes identifiable capabilities, not necessarily a physical computer.

```text
Physical: PC, server, IP camera, robot, NAS, phone
Software: browser worker, editor, CAD application, Home Assistant
Service: Gmail, Calendar, GitHub, Figma, cloud APIs
Model: GPT/Gemini/local LLM/vision model
Data: database, object store, vector store
Gateway: Zigbee/MQTT/Modbus/BLE bridge for devices too small to run a client
```

Weak devices do not need a full cognitive runtime. `agentos-node-micro` may only provide identity, heartbeat, discovery, event publication and governed capability invocation.

## Target UX

```text
PC / Mac       <= 3 clicks
Linux server   1 command
Mobile / IoT   1 QR scan + confirmation
Managed fleet  zero-touch policy enrollment
```

The current GitHub self-hosted-runner flow is Bootstrap v0 and remains useful as a development/recovery channel. It is not the intended end-user onboarding experience.

## Security invariants

1. Capability growth never implies authority growth.
2. Nodes cannot mint GovernanceRegistry profiles.
3. Join references/tickets are short-lived and single-use.
4. A Node cannot activate before all active capabilities have governance-owned profiles.
5. Local credentials never become reconciliation payloads.
6. Reconnect re-discovers capabilities; hardware/software changes do not silently inherit old authority.
7. Revocation must remain possible independently of Node cooperation.
8. Join UX may be one-touch; bootstrap authority remains minimal.
9. Bearer Join References should not be exposed in logs/process argv when a safer input channel is available.

> **UX may be one touch. Authority may not be one assumption.**
