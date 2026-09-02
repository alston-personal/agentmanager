# Spec Steward O3 Live Acceptance Runbook

Status: source-controlled acceptance procedure for AgentOS Core issue #197.

This runbook proves one narrow claim only: the durable `agentos-spec-steward` Employee can receive a governed ONE wake, checkpoint work, lose its first worker process/lease, resume in a later worker process, preserve Employee memory/thread state, and produce a sanitized terminal receipt.

It does **not** authorize protected-main publication, production deployment, arbitrary Node execution, shell/argv tunneling, credential access, session identity persistence, or GitHub Actions as a control-plane fallback.

## Acceptance boundary

The required chain is:

`canonical Employee -> Core Supervisor reconcile intent -> one_direct S4 delivery -> existing online wake-capable Node -> Node wake inbox -> governed Spec Steward worker -> lease generation 1 checkpoint -> expired lease / prior execution UNKNOWN -> governed resume wake -> fresh worker process -> lease generation 2+ -> memory/thread continuity -> terminal Employee receipt -> read-only acceptance inspector`

Static CI may prove the implementation contract, but static CI can never emit `SPEC_STEWARD_PERSISTENT_EMPLOYEE=VERIFIED`.

## Required preconditions

Use the accepted `core/integration` source SHA containing this runbook and worker code. Do not run the live acceptance from an unmerged feature branch.

The operator must provide these existing absolute paths/identities:

- `<ABS_EMPLOYEE_RUNTIME_ROOT>`: canonical Employee runtime root used by Core Supervisor.
- `<ABS_ONE_DATA_ROOT>`: existing ONE control-plane data root containing `realm/fabric.json` and `realm/nodes.json` for the same Realm.
- `<ABS_NODE_WAKE_ROOT>`: the wake inbox root already configured on the selected Node's `ThinClientPolicy.employee_wake_root`.
- `<ABS_WORKER_STATE_ROOT>`: separate Node-local Spec Steward worker state root. It must not overlap the canonical Employee runtime or wake root.
- `<NODE_ID>`: existing Node ID already registered in ONE.
- `<PRESENCE_ID>`: opaque operator-generated presence identifier. It is Employee-to-Node presence, not executor/session identity.

The selected Node must already be online and advertise `agent.employee.wake.deliver`. The presence CLI enforces this. If the Node lacks that capability, stop; this runbook does not authorize registering a new Node or broadening its capability set.

The ONE control plane and Node consumer must already be operating. Do not use GitHub Actions to replace ONE delivery.

## 1. Bootstrap canonical Spec Steward state

Run exactly once or idempotently repeat:

```bash
python -m agent_core.spec_steward_o3_cli \
  --runtime-root <ABS_EMPLOYEE_RUNTIME_ROOT> \
  bootstrap
```

Expected properties:

- canonical Employee ID is `agentos-spec-steward`;
- assignment ID is `spec-steward-o3-acceptance-v1`;
- the command may create the canonical Employee/work item/assignment on first execution;
- repeated bootstrap does not reset progressed thread, lease, terminal state, or live evidence;
- output always reports `verified_marker_emitted=false`.

A bootstrap-only inspect must remain blocked:

```bash
python -m agent_core.spec_steward_o3_cli \
  --runtime-root <ABS_EMPLOYEE_RUNTIME_ROOT> \
  inspect
```

Exit code `3` is expected until all live evidence exists.

## 2. Bind bounded Employee presence to the existing Node

```bash
python -m agent_core.spec_steward_presence_cli \
  --runtime-root <ABS_EMPLOYEE_RUNTIME_ROOT> \
  --one-data-root <ABS_ONE_DATA_ROOT> \
  --node-id <NODE_ID> \
  bind \
  --presence-id <PRESENCE_ID> \
  --ttl-seconds 300
```

This command must fail closed if ONE state is missing/mismatched, if the Node is offline/stale, or if the Node does not advertise `agent.employee.wake.deliver`.

Presence does not bind Employee identity to an executor/model/session. Output must keep `executor_identity_bound=false` and `credential_exposed=false`.

If the acceptance takes long enough that presence freshness is at risk, refresh the same owned presence without changing Employee identity:

```bash
python -m agent_core.spec_steward_presence_cli \
  --runtime-root <ABS_EMPLOYEE_RUNTIME_ROOT> \
  --one-data-root <ABS_ONE_DATA_ROOT> \
  --node-id <NODE_ID> \
  heartbeat \
  --presence-id <PRESENCE_ID> \
  --ttl-seconds 300
```

## 3. Run Core Supervisor with explicit S4 `one_direct` delivery

Run the existing Core Supervisor as an operator-controlled foreground/service process with delivery explicitly enabled:

```bash
AGENTOS_SUPERVISOR_DELIVERY_MODE=one_direct \
AGENTOS_SUPERVISOR_ONE_DATA_ROOT=<ABS_ONE_DATA_ROOT> \
python -m agent_core.core_supervisor_daemon \
  --runtime-root <ABS_EMPLOYEE_RUNTIME_ROOT>
```

Do not enable another transport. The Supervisor must persist the immutable S3 reconcile intent first, then the separate S4 delivery ledger. The worker will refuse to claim work unless it can find exactly one matching persisted authority chain for the wake:

- `kind=employee_wake`;
- `authority_policy_id=core-supervisor-employee-wake-v1`;
- `transport=one_direct`;
- `capability=agent.employee.wake.deliver`;
- exact Employee, assignment, wake, Node and presence;
- `dispatch_performed=true`;
- delivery still eligible for pre-claim execution.

A locally injected wake capsule without this Core-side authority evidence must not claim the Employee assignment.

## 4. First worker process: claim generation 1 and checkpoint only

Invoke the governed worker as a separate process. `--once` is mandatory:

```bash
python -m agentos_node.spec_steward_worker_cli \
  --runtime-root <ABS_EMPLOYEE_RUNTIME_ROOT> \
  --wake-root <ABS_NODE_WAKE_ROOT> \
  --worker-state-root <ABS_WORKER_STATE_ROOT> \
  --node-id <NODE_ID> \
  --lease-seconds 30 \
  --once
```

Expected result:

- `status=checkpointed`;
- `lease_generation=1`;
- assignment becomes active;
- thread head advances from the bootstrap head;
- no terminal Employee receipt exists for generation 1;
- no raw process ID/session ID/credential is persisted in the canonical receipt surface;
- the process exits after processing at most one wake.

Do not immediately restart the same lease as if nothing happened. The O3 acceptance specifically requires the first lease to cease being live so the next planner pass treats prior execution as `UNKNOWN` and emits a resume wake.

## 5. Resume in a fresh worker process

After generation 1 is no longer a live lease, the persistent Supervisor must plan and deliver the exact resume wake through ONE. Keep the Employee presence fresh if required.

Then invoke the same worker CLI again as a new OS process:

```bash
python -m agentos_node.spec_steward_worker_cli \
  --runtime-root <ABS_EMPLOYEE_RUNTIME_ROOT> \
  --wake-root <ABS_NODE_WAKE_ROOT> \
  --worker-state-root <ABS_WORKER_STATE_ROOT> \
  --node-id <NODE_ID> \
  --lease-seconds 30 \
  --once
```

Expected result:

- `status=completed`;
- lease generation is `2` or greater;
- the lease records `resume_required=true`, `prior_execution_state=unknown`, and a different `resumed_from_lease_id`;
- the worker observes the previous checkpoint and persists private Employee memory continuity;
- a privacy-safe fresh-process witness is created without raw PID/session identity;
- the terminal Employee receipt is sanitized and bound to the current lease generation/thread head.

Invoking both generations from the same worker process is not sufficient evidence; the worker intentionally refuses to create the fresh-executor witness in that case.

## 6. Let Supervisor observe claim/terminal state

Keep the Supervisor running until its S4 delivery ledger has observed both the initial and resume wake generations as governed deliveries (`claimed` or terminal-observed evidence as applicable).

Do not manually edit delivery ledgers, reconcile intents, lifecycle receipts, witness files, or memory evidence to satisfy the inspector.

## 7. Read-only acceptance inspection

Run:

```bash
python -m agent_core.spec_steward_o3_cli \
  --runtime-root <ABS_EMPLOYEE_RUNTIME_ROOT> \
  inspect
```

A source/live evidence chain ready for final attestation has:

- exit code `0`;
- `ready_for_live_marker=true`;
- `blocking_reasons=[]`;
- qualifying governed wake generations include generation `1` and the resumed terminal generation;
- `resumed_assignment_lease=true`;
- `fresh_executor_or_session_live_witness=true`;
- `private_memory_continuity=true`;
- `terminal_sanitized_employee_receipt=true`;
- `assignment_completed=true`;
- `carrier_and_authority_evidence=true`;
- `credential_and_session_identity_not_exposed=true`;
- `verified_marker_emitted=false`.

The last field is intentionally false. This source slice stops at `ready_for_live_marker`. A separate explicit live-attestation authority must decide whether to publish `SPEC_STEWARD_PERSISTENT_EMPLOYEE=VERIFIED`; neither CI nor this inspector may self-certify it.

## Failure and interruption rules

- If worker execution entered its side-effect boundary and then the process died, treat the prior attempt as `UNKNOWN`; do not blindly replay the same claimed execution.
- If S4 authority evidence is missing, wrong, ambiguous, GitHub-Actions-like, terminal/unknown before claim, or mismatched to Node/presence/wake, the governed worker must fail before acquiring the Employee lease.
- If presence expires, refresh/rebind only through the bounded presence utility and existing ONE Node authority; do not rewrite presence JSON manually.
- If ONE is unavailable, the acceptance is blocked. Do not fall back to GitHub Actions.
- If the Node capability is absent, the acceptance is blocked. Do not add shell or generic execution authority as a workaround.
- Preserve failed/unknown evidence for reconciliation. Do not delete canonical runtime evidence to make a retry appear clean.

## Acceptance record

For #197 closure, preserve at minimum:

- accepted Core source SHA containing the O3 worker/runbook;
- selected Realm and Node logical IDs (no credentials/session IDs);
- Supervisor S3/S4 reconcile and delivery evidence for initial + resume wakes;
- Employee lease generations and sanitized terminal receipt;
- privacy-safe fresh-process witness;
- Employee memory continuity evidence;
- final read-only inspector output;
- explicit live attestation that is external to static CI.

`core/integration` merge proves the implementation is accepted for integration. It does not by itself prove the Employee is OPERATING in the live Realm.
