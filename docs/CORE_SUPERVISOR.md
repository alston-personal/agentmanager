# AgentOS Core Supervisor

Status: **S3 integration candidate — persistent observe/plan loop, no execution dispatch**.

The Core Supervisor is the always-running reconciliation process for AgentOS. Employees remain durable organizational identities; they are not independent daemons. The Supervisor observes durable state and decides which assignment needs attention next.

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
                planned ReconcileIntent
                         |
                    S4 boundary
                         |
                         v
               governed ONE delivery
```

The invariant is **event != authority**. A GitHub Issue can trigger re-evaluation, but Issue prose is not an executable command and does not grant Node, executor, transport, capability, credential, or publication authority.

## What S3 does

The persistent service:

- holds a process singleton lock for one Employee runtime root;
- holds and heartbeats a durable Supervisor leader lease;
- scans durable Employee assignments;
- respects live Employee leases and blocked WorkItem dependencies;
- converts pending/resumable assignments into deterministic reconcile intents;
- journals a reconcile intent before any future delivery attempt;
- preserves `prior_execution_state=unknown` when an Employee execution lease expired without a terminal receipt;
- suppresses duplicate intents after restart;
- writes durable cycle receipts and a read-only health projection;
- increases polling backoff when state is unchanged;
- continues leader heartbeats during long idle backoff;
- survives process restart without deleting pending work.

## What S3 explicitly does not do

S3 does **not**:

- select a Node, executor, model, session, transport, or capability carrier;
- execute Issue text, shell commands, argv, scripts, or filesystem mutations;
- send a wake to a Node;
- claim an Employee assignment on behalf of an executor;
- invoke GitHub Actions as a control-plane fallback;
- publish to protected `main`;
- prove that the service is already installed or running on Oracle.

The source-controlled systemd unit uses `PrivateNetwork=true` intentionally. S3 has no network authority. S4 must cross a separate governed ONE delivery boundary.

## CLI

The production entrypoint is:

```text
python3 -m agent_core.core_supervisor_daemon
```

Read-only health:

```text
python3 -m agent_core.core_supervisor_daemon --health
```

One reconciliation cycle, useful for bounded local validation:

```text
python3 -m agent_core.core_supervisor_daemon --once
```

`AGENTOS_EMPLOYEE_RUNTIME_ROOT` must resolve to an absolute durable runtime path. `AGENTOS_DATA_ROOT` may be used as a parent fallback, in which case the Employee runtime is `<data-root>/employee-runtime`.

Non-secret configuration is documented in `.agent/scripts/agentos-core-supervisor.env.example`.

## Persistent-process safety

Two independent fences are used:

1. A long-held OS file lock at the runtime root prevents two local Supervisor daemon processes from operating concurrently.
2. A durable leader lease/generation protects restart/takeover semantics. A new process instance uses a new owner identity; takeover after an expired leader is recorded with prior owner state `unknown`.

The daemon never sleeps longer than half of the current leader lease without heartbeating, even when reconciliation backoff is longer than the lease.

## Durable state

Under the Employee runtime root:

```text
supervisor/
  process.lock
  leader.json
  state.json
  work-items/
  intents/
  cycles/
```

`intents/*.json` are S3 planned records with `dispatch_performed=false`. A merge of S3 therefore must never be interpreted as evidence that a Node was awakened or that an executor ran.

## systemd template

`.agent/scripts/agentos-core-supervisor.service` is a reference deployment template. Its write sandbox is intentionally limited to the configured Employee runtime area and its network namespace is private.

Before installation, the host-specific paths in the service and env file must be checked against the actual runtime layout. Installing/enabling/restarting the service is a separate governed runtime mutation and requires its own receipt/evidence.

**Repository merge != Oracle deployment != operating acceptance.**

## Acceptance path

- S1 deterministic reconcile kernel: integrated.
- S2 event/WorkItem intake: integrated.
- S3 persistent singleton loop: this slice.
- S4 governed ONE wake delivery: separate authority boundary.
- #197 Spec Steward: first end-to-end live Employee acceptance.

The final acceptance is not static CI. A real persistent Supervisor must notice a pending Spec Steward assignment without a user saying `繼續`, cause a governed wake through ONE, observe executor/session turnover, resume the same Employee/assignment/thread safely, and stop waking after a terminal receipt.
