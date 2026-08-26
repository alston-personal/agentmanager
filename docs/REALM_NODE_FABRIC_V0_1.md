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
9. experience/evidence feedback.

A Thin Client must not own canonical Realm memory, project state or cognition. Those belong to ONE.

## Generic-first capability model

v0.1 starts with generic capabilities:

- `shell.exec`
- `filesystem.read`
- `filesystem.write`
- `process.inspect`
- `tool.presence`
- `context.harvest`

Tool-specific semantic adapters are optional. For example, detecting Unity does not require a Unity adapter; `tool.presence + shell.exec + filesystem.*` can already expose useful generic execution. Repeated validated recipes may later be promoted to semantic capabilities such as `unity.project.build`.

## Governance boundary

ONE never sends an unrestricted shell string. A task capsule describes executable, argv, cwd, timeout and path scope. The Thin Client performs local validation before execution and emits a receipt. Capability discovery, authorization and execution are separate decisions.

## Oracle canonical identity

The existing Oracle deployment is canonicalized as one Core Node, not re-enrolled as a duplicate client:

- role: `core`
- node id: `core-oracle-01`
- GitHub self-hosted runner: Core GitHub adapter / bootstrap ingress
- ubuntu and agentos-node: executor identities inside the same Core Node

Future client Nodes should not require GitHub Actions runners or GitHub credentials.

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
