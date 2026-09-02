# AgentOS Shared Employee Worker Host

Status: **source integration candidate; live deployment/operating acceptance pending**.

The Employee Worker Host is the Node-side process boundary between an already-delivered typed Employee wake capsule and a source-registered bounded Employee adapter. It is one shared host for many Employees/roles; it is not one daemon per role.

## Boundary

```text
Core Supervisor
  -> governed S4 one_direct delivery
  -> ThinClient typed Employee wake inbox
  -> Shared Employee Worker Host
  -> source-controlled adapter registry
  -> fresh bounded adapter process
  -> adapter re-checks canonical Supervisor awaiting_claim authority
  -> Employee lifecycle claim/checkpoint/receipt
```

The host does **not** grant Employee claim authority. It does not select arbitrary executables, argv, modules, providers, models, sessions, URLs, credentials, transports, or publication targets.

## Source-controlled adapter registry

`governance/employee-worker-adapters.json` contains only bounded logical adapter metadata and a `runner_kind` enum. Executable/module/argv strings are forbidden from the registry. The current source slice registers only the bounded `spec_steward_o3` adapter.

The wake capsule cannot choose `runner_kind`. Adapter resolution requires the exact Employee, assignment, roles, and skills declared by source-controlled policy.

## Exact wake binding

The deployment surface pins one selected wake capsule for the whole child launch. The bounded child receives only:

- exact `wake_id`;
- exact `presence_generation`;
- fixed runtime/wake/worker-state roots;
- fixed Node identity;
- bounded lease timeout.

The governed Spec Steward adapter then re-checks the exact immutable Supervisor reconcile intent and the separate `awaiting_claim` S4 delivery ledger before Employee claim.

A child result is trusted only when its Employee, assignment, wake id, presence generation, lease generation, schema, and privacy flags match the exact host dispatch. Mismatch becomes `unknown`.

## Crash and replay semantics

The host persists a dispatch ledger with `status=launching` **before** crossing the child process boundary.

If the host restarts and sees a prior `launching` state, it records:

`employee_worker_prior_launch_unknown`

and does not blindly replay the wake. The child may already have changed Employee state. Timeout, OS launch failure, malformed output, or ambiguous output likewise becomes `unknown` rather than being retried as though no side effect occurred.

Raw child stderr/stdout are not persisted in the canonical dispatch ledger.

## Credential isolation

The child process receives a small allowlisted environment. It does not inherit host GitHub/ONE/AgentOS tokens or arbitrary environment variables. The shared host does not move Realm credentials into the Employee adapter.

The Linux user service keeps `PrivateNetwork=true`, `NoNewPrivileges=true`, `ProtectSystem=strict`, reads the configured wake inbox read-only, and writes only the Employee runtime plus dedicated host/worker state roots.

## Activation gate

Repository merge does not activate this execution boundary.

CORE installation enables the shared host only when the host-local deployment configuration explicitly sets:

```text
AGENTOS_CORE_EMPLOYEE_WORKER_HOST_ENABLE=1
AGENTOS_EMPLOYEE_WAKE_ROOT=/absolute/already-existing/wake-root
AGENTOS_EMPLOYEE_WORKER_NODE_ID=<exact-node-id>
```

The installer refuses to create a missing wake inbox. The Node's typed wake policy and Worker Host must therefore converge on the same already-configured wake root before activation.

## Non-claims

Static CI can verify dispatch determinism, exact-wake binding, process isolation, crash/UNKNOWN behavior, service sandboxing, and fail-closed installation. It cannot prove that Oracle or another Node is currently running the service or that a real Employee executor/session transition occurred.

Live acceptance remains separate and requires governed runtime mutation plus receipts. Source merge alone does not establish `CORE_SUPERVISOR_PERSISTENT_RECONCILIATION=VERIFIED` or `SPEC_STEWARD_PERSISTENT_EMPLOYEE=VERIFIED`.
