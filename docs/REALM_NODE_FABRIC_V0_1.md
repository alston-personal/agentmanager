# AgentOS Realm Node Fabric v0.1

Status: draft implementation contract

## Purpose

Realm Node Fabric is the layer that turns a collection of independent machines into one governed Realm capability surface. A Node contributes local resources; ONE owns Realm state, cognition, routing and governance.

## Roles

- `realm`: sovereign state/cognition/governance boundary.
- `core`: the unique logical ONE host for a Realm. v0.1 assumes one active core.
- `client`: an enrolled execution host. Clients do not host canonical Realm state.
- `executor`: a capability provider inside a Node (shell, filesystem, browser, Antigravity, GPU, camera, etc.). Executor is not a Node identity.
- `capability`: a structured operation an executor can provide. Presence does not imply authorization.

## v0.1 Node runtime contract

A Thin Client must provide:

1. persistent Node identity;
2. Realm enrollment metadata;
3. heartbeat;
4. capability advertisement;
5. governed task receipt;
6. governed local execution;
7. artifact references;
8. execution receipt;
9. experience/evidence feedback;
10. transactional OTA runtime update with verified rollback.

A Thin Client must not own canonical Realm memory, project state or cognition. Those belong to ONE.

## Transactional OTA contract

A Thin Client OTA update MUST be fail-safe and must not overwrite the last known-good runtime in place.

Required sequence:

1. download the candidate runtime into a separate staging/version directory;
2. verify source identity, expected commit/version, file manifest and integrity before activation;
3. run static/import/configuration checks against the staged candidate without replacing the active runtime;
4. start or probe the candidate sufficiently to prove heartbeat and required baseline capabilities;
5. retain the current runtime as the last-known-good rollback target;
6. switch the active runtime atomically only after candidate validation passes;
7. run post-switch health/readiness acceptance, including heartbeat and governed task receipt;
8. if activation or post-switch acceptance fails, automatically restore and restart the last-known-good runtime;
9. emit an OTA receipt recording candidate version, previous version, validation results, activation result and rollback result without secrets.

An OTA operation is successful only after post-switch acceptance passes. A downloaded or copied candidate is not considered deployed. Update failure MUST leave the Node operating on the previous known-good runtime whenever that runtime was healthy before the update.

## Generic-first capability model

v0.1 starts with generic capabilities:

- `shell.exec`
- `filesystem.read`
- `filesystem.write`
- `process.inspect`
- `tool.presence`
- `context.harvest`

Tool-specific semantic adapters are optional. For example, detecting Unity does not require a Unity adapter; `tool.presence + shell.exec + filesystem.*` can already expose useful generic execution. Repeated validated recipes may later be promoted to semantic capabilities such as `unity.project.build`.

## Thin Client adapter contract

The Thin Client is the stable Node runtime and transport boundary. Device-specific
or runtime-specific behavior MUST be contributed through an adapter instead of
adding another Node transport.

An adapter:

- has a stable local `adapter_id`;
- declares one or more capability IDs;
- exposes sanitized topology metadata;
- executes only tasks for its declared capabilities;
- returns structured results that the Thin Client wraps in the normal governed
  Node receipt;
- does not own Realm identity, enrollment credentials, heartbeat, task polling,
  receipt transport, canonical memory or cognition.

Configured external adapters are explicit local authority via
`AGENTOS_NODE_ADAPTERS`; the Thin Client does not scan arbitrary modules or
devices and silently grant capabilities.

The Node manifest projects adapter topology into ONE so routing can distinguish
the Node from the hardware/runtime providers attached to it.

Example:

```text
glasses-01 (Node / Thin Client)
├─ camera-adapter
│  ├─ camera.capture
│  └─ camera.status
├─ xreal-adapter
│  ├─ display.overlay
│  └─ head.pose
└─ audio-adapter
   ├─ audio.capture
   └─ audio.play
```

Cross-Node sharing is Realm-mediated, not implicit peer trust:

```text
Node A capability request
        ↓
ONE / Realm policy + routing
        ↓
authorized Node B capability
        ↓
receipt / artifact reference
        ↓
Node A / requesting Agent
```

A Node becoming reachable does not authorize another Node to invoke it directly.
Capability declaration, Realm membership, routing and execution authorization
remain separate decisions.

## Governance boundary

ONE never sends an unrestricted shell string. A task capsule describes executable, argv, cwd, timeout and path scope. The Thin Client performs local validation before execution and emits a receipt. Capability discovery, authorization and execution are separate decisions.

## Oracle identities

Oracle has two deliberately distinct AgentOS identities:

- `oracle-core-node` — the ONE Core identity. It owns Realm/control-plane responsibilities and must not be treated as a generic shell executor.
- `oracle-exec` — the native Linux Thin Client execution identity introduced by #600. It joins the Realm through normal Node transport, emits heartbeat, pulls governed tasks, and returns receipts independently of SSH and the GitHub self-hosted runner.

The GitHub self-hosted runner remains an adapter/bootstrap ingress, not the execution Node transport itself. Linux OS users such as `ubuntu` and `agentos-node` are executor/runtime accounts, not Node identities.

This separation is required so a failure of SSH or the GitHub runner does not remove the controller's ability to diagnose and recover Oracle through bounded semantic maintenance actions.

## Before/After ONE benchmark

Every new Client must record a standalone baseline and an ONE-enabled result using equivalent tasks. The benchmark measures at least:

- task success;
- repeated-error count;
- user clarification count;
- continuity recovery;
- Realm capability usage;
- inherited cognition usage;
- new evidence returned to ONE.

Recommended phases:

- `T0`: standalone baseline, ONE context disabled;
- `T1`: enroll into Realm;
- `T2`: same/equivalent task with ONE enabled;
- `T3`: return execution evidence/experience;
- `T4`: cross-node re-test proving that another Node can benefit from the returned cognition.

The acceptance target is not merely connectivity. It is measurable `ONE cognitive uplift` while keeping the same local executor/model/tooling as much as possible.

## Cognition feedback

Receipts may reference `cognition_ids_used`. A successful execution can add supporting evidence; a contradiction can add a counterexample. ONE, not the Client, owns confidence updates, scope refinement, promotion and demotion.

Suggested cognition lifecycle:

`emerging -> observed -> validated -> trusted -> canonical -> universal_candidate -> universal_canonical`

## Deferred from v0.1

- QR enrollment UX (protocol first, UX second)
- browser bridge semantic adapter
- GPU artifact routing
- mobile client
- camera/sensor handoff
- Universal ONE federation

These must reuse the same Node Fabric protocol rather than creating parallel transports.
