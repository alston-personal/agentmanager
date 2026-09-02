# AgentOS Core Supervisor

Status: **S4 source integration candidate — persistent reconciliation with explicit governed ONE wake delivery; live Oracle operating acceptance is still pending**.

The Core Supervisor is the long-running reconciliation process for AgentOS. Employees remain durable organizational identities; they are not independent daemons. The Supervisor observes durable state, journals which Employee assignment needs attention, and may cross the S4 wake boundary only when an explicit machine policy authorizes the exact persisted wake through the existing ONE control plane.

## Core model

```text
Issue event / Realm message / timer / dependency / user goal
                         |
                         v
                 bounded event intake
                         |
                         v
                      WorkItem
                         |
                         v
             Employee durable assignment
                         |
                         v
                Core Supervisor S1-S3
             observe -> reconcile -> journal
                         |
                         v
          immutable planned ReconcileIntent
                         |
                         v
                 S4 authority policy
                         |
                 exact-current-wake fence
                         |
                         v
           existing Employee presence in ONE
                         |
                         v
        ControllerService -> existing ONE queue
                         |
                         v
               fixed Node wake inbox
                         |
                         v
              authenticated Node receipt
                         |
                         v
                    awaiting_claim
                         |
                         v
          Employee lifecycle lease / receipt
```

The invariant is **event != authority**. A GitHub Issue can trigger re-evaluation, but Issue prose is not an executable command and does not grant Node, executor, transport, capability, credential, publication, or protected-branch authority.

## S1-S3 persistent reconciliation

The persistent service:

- holds a process singleton lock for one Employee runtime root;
- holds and heartbeats a durable Supervisor leader lease;
- scans durable Employee assignments;
- respects live Employee leases and blocked WorkItem dependencies;
- converts pending/resumable assignments into deterministic reconcile intents;
- journals a reconcile intent before any delivery attempt;
- preserves `prior_execution_state=unknown` when an Employee execution lease expired without a terminal receipt;
- suppresses duplicate intents after restart;
- writes durable cycle receipts and a read-only health projection;
- increases polling backoff when state is unchanged;
- continues leader heartbeats during long idle backoff;
- survives process restart without deleting pending work.

The S3 reconcile record is immutable evidence. S4 does not rewrite it to claim that delivery happened.

## S4 governed wake delivery

S4 is opt-in and uses `governance/core-supervisor-delivery.json` plus the existing authority-driven `governance/transport-routing.json`.

For the current `employee_wake` reconcile kind, S4 authorizes only:

- capability: `agent.employee.wake.deliver`;
- intent class: `control_plane`;
- transport: explicit `one_direct`;
- an exact already-persisted `EmployeeWakeIntent`.

It explicitly does **not** grant:

- Employee assignment claim authority;
- executor/model/provider/session selection authority;
- generic shell, argv, filesystem, desktop, URL, or credential authority;
- GitHub Actions fallback authority.

Capability availability is checked only after authority is resolved. An online Node or an available runner never grants authority by itself.

### Exact-current-wake fence

A persisted wake can become stale after planning. For example, another executor may claim the assignment or the assignment goal/thread/role/skill state may change before delivery.

Before a new delivery attempt, S4 recomputes the planner only as a validation read and requires the complete current wake projection to match the exact persisted wake. It does not replace or re-plan the delivery input. A mismatch becomes `superseded` and does not cross ONE.

### Delivery ledger

S4 writes a separate ledger:

```text
supervisor/
  intents/                  # immutable S3 selection evidence
  deliveries/               # S4 authority/delivery progression
  cycles/
  leader.json
  state.json
```

Important delivery states include:

- `blocked`: authority, presence, or pre-dispatch prerequisite unavailable;
- `queued`: exact wake entered the existing ONE Node queue;
- `awaiting_claim`: Node accepted the fixed wake capsule, but no executor owns the assignment yet;
- `claimed`: a live Employee lifecycle lease at the expected generation is observed;
- `unknown`: delivery crossed an ambiguous external boundary and is not blindly retried to the same presence;
- `failed`: terminal Node wake failure for that presence generation;
- `superseded`: the persisted wake is no longer the exact current wake;
- `terminal_observed`: the underlying assignment is already terminal.

A Node receipt is **not** treated as execution success. `wake_delivery.accepted=true` proves only that the Node wake inbox accepted the bounded capsule; it must also prove `executor_invoked=false` and `credential_exposed=false`. The Supervisor remains in `awaiting_claim` until a real Employee lifecycle lease is observed.

If an Employee moves to a strictly newer presence generation before any assignment claim, the same exact wake may follow that new presence. The same presence is not blindly re-sent. If an execution lease later expires, S1 produces a new deterministic resume wake with `prior_execution_state=unknown`.

## No shadow ONE

S4 reuses the existing ONE control plane. `EmployeeWakeDelivery` refuses to dispatch unless both the existing Realm fabric and Node Registry already exist, carry non-empty Realm identities, and identify the same Realm.

The Supervisor must never initialize a missing `fabric.json` or `nodes.json` as a side effect of enabling delivery. A missing or mismatched control-plane store is a fail-closed configuration error, not permission to create a second Realm.

## CLI and opt-in configuration

The production entrypoint remains:

```text
python3 -m agent_core.core_supervisor_daemon
```

Read-only health:

```text
python3 -m agent_core.core_supervisor_daemon --health
```

One bounded cycle:

```text
python3 -m agent_core.core_supervisor_daemon --once
```

`AGENTOS_EMPLOYEE_RUNTIME_ROOT` must be an absolute durable runtime path. Non-secret configuration is documented in `.agent/scripts/agentos-core-supervisor.env.example`.

The default is deliberately:

```text
AGENTOS_SUPERVISOR_DELIVERY_MODE=disabled
```

S4 is enabled only by an explicit host-local configuration such as:

```text
AGENTOS_SUPERVISOR_DELIVERY_MODE=one_direct
AGENTOS_SUPERVISOR_ONE_DATA_ROOT=/home/ubuntu/agent-data
```

Enabling `one_direct` attaches the S4 coordinator to that process; repository merge by itself does not enable it.

## Persistent-process safety

Two independent fences remain active:

1. A long-held OS file lock at the runtime root prevents two local Supervisor daemon processes from operating concurrently.
2. A durable leader lease/generation protects restart/takeover semantics. A new process instance uses a new owner identity; takeover after an expired leader is recorded with prior owner state `unknown`.

Every S4 advance requires the current Supervisor leader generation before crossing authority. The daemon never sleeps longer than half of the current leader lease without heartbeating, even when reconciliation backoff is longer than the lease.

## systemd sandbox

`.agent/scripts/agentos-core-supervisor.service` remains the safe S3 base template:

- `PrivateNetwork=true`;
- `NoNewPrivileges=true`;
- `ProtectSystem=strict`;
- write access limited to the Employee runtime root.

S4 does not silently widen the base unit. The optional `.agent/scripts/agentos-core-supervisor-delivery.conf.example` is a separate systemd drop-in that adds write access only to the existing ONE `realm/` directory needed by the local file-backed `one_direct` queue. `PrivateNetwork=true` remains in force; current S4 does not need generic outbound networking.

Before installation, host-specific paths must be checked against the actual canonical runtime. Installing a drop-in, changing host-local env, enabling/restarting the service, creating a persistent Employee presence, or running a live Spec Steward assignment are governed runtime mutations and need independent receipts/evidence.

**Repository merge != Oracle deployment != operating acceptance.**

## Acceptance path

- S1 deterministic reconcile kernel: integrated.
- S2 event/WorkItem intake: integrated.
- S3 persistent singleton loop: integrated.
- #197 O2 exact governed Employee wake carrier: integrated.
- S4 Supervisor -> exact persisted wake -> ONE delivery coordinator: this source slice.
- #197 O3 Spec Steward: first real persistent Employee operating acceptance.

Static hosted CI can prove deterministic state transitions and the local ONE queue/Node receipt contract, but it cannot prove that Oracle is currently running the service or that a real executor/session transition occurred.

The final acceptance requires a live persistent Supervisor to notice a pending Spec Steward assignment without a user saying `繼續`, deliver the exact wake through the authorized ONE path, observe a real executor claim/checkpoint, survive executor/session turnover or lease expiry, resume the same Employee/assignment/thread safely, persist a terminal sanitized Employee receipt, and stop waking terminal work.

Success markers remain:

- `CORE_SUPERVISOR_PERSISTENT_RECONCILIATION=VERIFIED`
- `SPEC_STEWARD_PERSISTENT_EMPLOYEE=VERIFIED`

Neither marker may be claimed from source merge or static CI alone.
