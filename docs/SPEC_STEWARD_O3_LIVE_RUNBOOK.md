# Spec Steward O3 Live Acceptance Runbook

Status: **source-controlled live acceptance procedure for AgentOS Core issue #197; runtime execution requires separate explicit authorization**.

This runbook proves one narrow operating claim: the durable `agentos-spec-steward` Employee can be noticed by the persistent Core Supervisor, receive a governed ONE wake on an existing Node, be launched automatically by the shared Employee Worker Host, checkpoint in one fresh bounded child process, resume after lease loss in a later fresh child process, preserve Employee memory/thread state, and produce a sanitized terminal receipt **without an operator manually invoking the worker for either generation**.

It does **not** authorize protected-main publication, production deployment by itself, arbitrary Node execution, shell/argv tunneling, credential access, session identity persistence, or GitHub Actions as a control-plane fallback.

## Acceptance boundary

The required chain is:

`canonical Employee -> persistent Core Supervisor -> immutable S3 reconcile intent -> governed one_direct S4 delivery -> existing online wake-capable Node -> ThinClient typed wake inbox -> persistent shared Employee Worker Host -> source-registered bounded Spec Steward child -> lease generation 1 checkpoint -> expired lease / prior execution UNKNOWN -> Supervisor resume wake -> fresh bounded child process -> lease generation 2+ -> memory/thread continuity -> terminal Employee receipt -> read-only acceptance inspector`

Static CI may prove the implementation contract, but static CI can never emit `SPEC_STEWARD_PERSISTENT_EMPLOYEE=VERIFIED`.

## Required preconditions

Use an accepted `core/integration` SHA that contains the persistent Supervisor, typed Node wake policy, shared Employee Worker Host, strict service deployment semantics, and this runbook. Do not run live acceptance from an unmerged feature branch.

The operator must identify these existing absolute paths/identities before mutation:

- `<ABS_EMPLOYEE_RUNTIME_ROOT>`: canonical Employee runtime root used by Core Supervisor.
- `<ABS_ONE_DATA_ROOT>`: existing ONE control-plane data root containing `realm/fabric.json` and `realm/nodes.json` for the same Realm.
- `<ABS_NODE_WAKE_ROOT>`: wake inbox root already configured in the selected Node's `ThinClientPolicy.employee_wake_root`.
- `<ABS_WORKER_HOST_STATE_ROOT>`: dedicated shared Worker Host dispatch-state root.
- `<ABS_WORKER_STATE_ROOT>`: dedicated bounded Employee adapter state root.
- `<NODE_ID>`: existing Node ID already registered in ONE.
- `<PRESENCE_ID>`: opaque operator-generated Employee-to-Node presence identifier, never executor/session identity.

The runtime, wake, host-state, and worker-state roots must be distinct and non-overlapping.

The selected Node must already be online and advertise `agent.employee.wake.deliver`. If that capability is absent, stop. This runbook does not authorize registering a new Node, inventing Node identity, or broadening generic shell/filesystem authority.

The ONE control plane and the Node consumer must already be operating. GitHub Actions may deploy accepted source when explicitly authorized, but it is never the Employee control-plane carrier.

## 0. Governed deployment configuration

Before a live deployment, host-local configuration must deliberately converge the accepted source with the existing ONE/Node state.

For the Core host:

```text
AGENT_MODE=CORE
AGENTOS_CORE_SUPERVISOR_ENABLE_ONE_DIRECT=1
AGENTOS_CORE_EMPLOYEE_WORKER_HOST_ENABLE=1
AGENTOS_EMPLOYEE_WAKE_ROOT=<ABS_NODE_WAKE_ROOT>
AGENTOS_EMPLOYEE_WORKER_NODE_ID=<NODE_ID>
```

The installer must not create a missing wake inbox. `AGENTOS_EMPLOYEE_WAKE_ROOT` must already exist and must be the same inbox the selected Node uses for typed Employee wake delivery.

A successful native Linux installation must leave both of these active:

```text
agentos-core-supervisor.service
agentos-employee-worker-host.service
```

If native systemd installation was attempted but failed, deployment must fail rather than downgrade to a manifest-only success.

Changing host-local configuration, deploying a source ref, enabling/restarting either service, or changing Node policy is a governed runtime mutation and requires explicit authorization outside this runbook.

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
- first execution may create canonical Employee/work item/assignment;
- repeated bootstrap does not reset progressed thread, lease, terminal state, or live evidence;
- output reports `verified_marker_emitted=false`.

A bootstrap-only inspect must remain blocked:

```bash
python -m agent_core.spec_steward_o3_cli \
  --runtime-root <ABS_EMPLOYEE_RUNTIME_ROOT> \
  inspect
```

Exit code `3` is expected until the live evidence chain is complete.

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

This must fail closed if ONE state is missing/mismatched, the Node is offline/stale, or the Node does not advertise `agent.employee.wake.deliver`.

Presence does not bind Employee identity to an executor/model/session. Output must keep `executor_identity_bound=false` and `credential_exposed=false`.

Refresh the same owned presence when needed:

```bash
python -m agent_core.spec_steward_presence_cli \
  --runtime-root <ABS_EMPLOYEE_RUNTIME_ROOT> \
  --one-data-root <ABS_ONE_DATA_ROOT> \
  --node-id <NODE_ID> \
  heartbeat \
  --presence-id <PRESENCE_ID> \
  --ttl-seconds 300
```

## 3. Prove persistent Supervisor delivery without an operator wake command

The persistent `agentos-core-supervisor.service` must already be active with the explicitly enabled `one_direct` configuration. Do **not** run a one-shot manual delivery command as the acceptance carrier.

After bootstrap/presence state makes the assignment eligible, the service itself must:

1. observe the pending/resumable assignment;
2. persist the immutable S3 reconcile intent;
3. resolve the explicit S4 authority policy;
4. deliver the exact wake through existing ONE;
5. reconcile a successful Node wake receipt to `awaiting_claim`.

Required authority chain:

- `kind=employee_wake`;
- `authority_policy_id=core-supervisor-employee-wake-v1`;
- `transport=one_direct`;
- `capability=agent.employee.wake.deliver`;
- exact Employee, assignment, wake, Node and presence;
- `dispatch_performed=true`;
- Node-acknowledged pre-claim state `awaiting_claim`.

A merely `queued` ONE task or a locally injected capsule is not execution authority.

## 4. Generation 1 must be launched automatically by the shared Worker Host

Do **not** invoke `agentos_node.spec_steward_worker_cli` manually.

The persistent `agentos-employee-worker-host.service` must observe the typed wake inbox, resolve the source-controlled `spec-steward-o3` adapter, pin the exact `wake_id + presence_generation`, and launch one fresh bounded child process.

Expected generation-1 result:

- host dispatch crosses `launching` before child execution;
- child result is exact-bound to the selected wake;
- `status=checkpointed`;
- `lease_generation=1`;
- assignment becomes active;
- thread head advances;
- no terminal Employee receipt exists for generation 1;
- raw PID/session identity/credential is not persisted;
- child exits after the bounded wake;
- Worker Host remains persistent and does not become the Employee identity.

The acceptance fails if an operator had to manually invoke the bounded worker to make generation 1 occur.

## 5. Lease loss must become UNKNOWN, then resume automatically in a fresh child

Allow generation 1 to cease being a live lease. Do not edit lease state or pretend the first child had no side effects.

The persistent Supervisor must then observe the expired active assignment and produce a new deterministic resume wake with:

- `resume_required=true`;
- `prior_execution_state=unknown`;
- next expected lease generation.

The resume wake must again cross ONE and reach `awaiting_claim`.

Without an operator manually invoking the worker, the shared Worker Host must launch a **new** bounded child process for the exact resume wake.

Expected resumed result:

- `status=completed`;
- lease generation is `2` or greater;
- `resume_required=true` and `prior_execution_state=unknown` are preserved;
- `resumed_from_lease_id` points to the prior generation;
- a distinct privacy-safe process-instance witness proves the process boundary changed;
- previous checkpoint/thread state is observed;
- private Employee memory continuity is persisted;
- terminal Employee receipt is sanitized and bound to the current lease/thread.

The same child process handling both generations is insufficient evidence. Manual worker invocation for the second generation is also insufficient evidence for the autonomous O3 claim.

## 6. Let Supervisor observe terminal state and stop waking completed work

Keep the persistent services running until the Supervisor delivery ledger observes claim/terminal progression for both wake generations.

After terminal completion, observe at least one later Supervisor reconciliation cycle and require that no new Employee wake is delivered for the terminal assignment.

Do not manually edit delivery ledgers, reconcile intents, lifecycle receipts, Worker Host dispatch ledgers, witness files, or memory evidence.

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
- governed wake generations include generation `1` and the resumed terminal generation;
- `resumed_assignment_lease=true`;
- `fresh_executor_or_session_live_witness=true`;
- `private_memory_continuity=true`;
- `terminal_sanitized_employee_receipt=true`;
- `assignment_completed=true`;
- `carrier_and_authority_evidence=true`;
- `credential_and_session_identity_not_exposed=true`;
- `verified_marker_emitted=false`.

Additionally retain sanitized Worker Host evidence showing two exact-bound child launches at different Employee lease generations, with no credential/session identity exposure and no blind replay state.

The final field intentionally remains false. A separate explicit live-attestation authority must decide whether to publish `SPEC_STEWARD_PERSISTENT_EMPLOYEE=VERIFIED`; neither CI, the Worker Host, nor this inspector may self-certify it.

## Failure and interruption rules

- Host dispatch is journaled before child launch. If a prior dispatch remains `launching` after host interruption, classify the attempt as `UNKNOWN`; never blindly replay it.
- If child launch times out, OS launch status is ambiguous, or child output cannot be exact-bound to the selected wake, preserve `UNKNOWN` evidence.
- If S4 authority evidence is missing, wrong, ambiguous, GitHub-Actions-like, or mismatched to Node/presence/wake, the bounded adapter must fail before Employee claim.
- If presence expires, refresh/rebind only through the bounded presence utility and existing ONE Node authority; never rewrite presence JSON manually.
- If ONE is unavailable, acceptance is blocked. Do not fall back to GitHub Actions.
- If the Node capability is absent, acceptance is blocked. Do not add shell or generic execution authority as a workaround.
- Preserve failed/unknown evidence for reconciliation. Do not delete canonical runtime evidence to make a retry appear clean.

## Acceptance record

For #197 closure, preserve at minimum:

- accepted Core source SHA containing this runbook and shared Worker Host;
- selected Realm and Node logical IDs, without credentials/session IDs;
- deployment source ref + exact SHA and native service-install result;
- active persistent Supervisor + shared Worker Host evidence;
- Supervisor S3/S4 reconcile/delivery evidence for initial + resume wakes;
- exact-bound Worker Host dispatch evidence for both child generations;
- Employee lease generations and sanitized terminal receipt;
- privacy-safe fresh-process witness;
- Employee memory/thread continuity evidence;
- evidence that terminal work is no longer re-woken;
- final read-only inspector output;
- explicit live attestation external to static CI.

`core/integration` merge proves the implementation is accepted for integration. It does not by itself prove the Employee is OPERATING in the live Realm.
