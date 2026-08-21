# Runtime Dispatcher

## Purpose

The Control Plane already guarantees durable Canonical IR tasks, capability leases,
result verification, and continuation enqueue. The Runtime Dispatcher adds the
missing **wake-up decision**:

```text
Canonical IR
    ↓
Control Plane task
    ↓
Runtime Dispatcher
    ├─ online local/remote node → wait for lease (local-first)
    ├─ GitHub Actions target    → workflow_dispatch
    └─ web-agent bridge         → authenticated webhook
```

The dispatcher does **not** execute tasks and does not own continuation lineage.
Every runtime still has to lease the task from the Control Plane. This makes task
leasing the final execution fence even if an external wake-up is duplicated.

## Routing policy

Default routing is deliberately conservative:

1. A task explicitly targeted to a runtime keeps that target.
2. If an online pull-based node already advertises the required capability, the
   task waits for that node instead of spending a push/cloud execution.
3. Otherwise, the lowest-priority-number push target supporting the capability is
   selected.
4. Canonical IR may opt into push preference with:

```json
{
  "context": {
    "runtime_policy": {
      "prefer_push": true,
      "preferred_target": "github-actions-worker",
      "allowed_kinds": ["github_actions"],
      "deny_targets": []
    }
  }
}
```

`preferred_target`, `allowed_kinds`, and `deny_targets` are optional.

## Durable dispatch state

Push attempts are recorded in the Control Plane SQLite database in
`runtime_dispatches`.

A `(task_id, target_id)` pair keeps:

- stable `dispatch_id`
- target kind
- state (`dispatching`, `dispatched`, `failed`)
- attempt count
- external reference
- last error
- timestamps

Repeated calls do not re-trigger an already successful dispatch. A dispatcher
that crashed while in `dispatching` may retry after the configured stale timeout.
A duplicate external wake-up is still safe because only one runtime can lease the
task.

## GitHub Actions transport

`GitHubActionsDispatchTransport` calls GitHub's workflow dispatch API and passes:

- `control_plane_url`
- stable `runtime_id`
- `dispatch_id`

The workflow then runs in **gateway mode** and leases the already-targeted task.

The Control Plane URL must be HTTPS because a GitHub-hosted runner cannot safely
use a loopback or plaintext Core endpoint.

Example Core configuration:

```bash
export AGENTOS_CONTROL_PLANE_TOKEN='...'
export AGENTOS_CONTROL_PLANE_PUBLIC_URL='https://agentos.example.com'
export AGENTOS_GITHUB_TOKEN='...'
export AGENTOS_GITHUB_REPOSITORY='alston-personal/agentmanager'
export AGENTOS_GITHUB_REF='main'
export AGENTOS_GITHUB_RUNTIME_ID='github-actions-worker'
export AGENTOS_GITHUB_CAPABILITIES='agentos.ir.validate,ci.test'

python3 scripts/distributed_gateway.py --host 127.0.0.1 --port 8765
```

Expose the local gateway through an authenticated HTTPS reverse proxy/tunnel; do
not bind a bearer-token gateway directly to the public Internet without TLS.

## Web-agent bridge transport

`WebhookDispatchTransport` emits `agentos.runtime-dispatch/v1` to an authorized
HTTPS bridge. The bridge can use `WebAgentAdapter` to deliver the Canonical IR to
ChatGPT, Gemini, or another browser/API agent and then complete the task through
the Control Plane.

The dispatcher only wakes the bridge. It does not trust a web model to fabricate
`parent_ir_id`, `project_id`, `hop_count`, or continuation digests.

## Closing the continuation loop

`DispatchingGatewayService` wraps the normal HTTP gateway:

```text
submit IR
  → enqueue task
  → dispatch_task(task)

runtime completes
  → verify result
  → enqueue continuation (when auto_continue=true)
  → dispatch_task(continuation task)
```

This is the first slice where AgentOS can automatically move from “the next task
exists” to “the next eligible runtime is actively woken”.
