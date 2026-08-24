# Private Continuity Mirror

Distributed AgentOS uses the Control Plane as the authoritative task/Canonical IR state. Some agents cannot reach that HTTP endpoint directly—for example, a ChatGPT session may have a GitHub connector but no custom bearer-authenticated network route to the Control Plane.

The **Private Continuity Mirror** solves that read-path problem without making GitHub the Control Plane.

## Data flow

```text
IDE / Runtime / Provider
        ↓
   Control Plane
        ↓ submit / complete
 durable project state
        ↓ best-effort mirror
private my-agent-data repository
        ↓
projects/<project-id>/continuity/latest.json
        ↓
GitHub-connected ChatGPT / other connector-only agent
```

The mirror is deliberately one-way and non-authoritative. A mirror outage must not fail task submission or completion.

## Protocol

The file uses:

```text
agentos.continuity-mirror/v1
```

Example shape:

```json
{
  "protocol": "agentos.continuity-mirror/v1",
  "project_id": "agentmanager",
  "recommended_action": "wait",
  "current_source": "task_input",
  "current_ir_digest": "...sha256...",
  "canonical_ir": {},
  "latest_task": {
    "taskId": "...",
    "status": "submitted",
    "capability": "code.implement"
  }
}
```

`current_ir_digest` is recomputed from the Canonical IR using the normal Canonical IR digest implementation. Connector agents should reject or flag a checkpoint whose digest does not match.

## Core configuration

```bash
AGENTOS_CONTINUITY_MIRROR_REPOSITORY=alston-personal/my-agent-data
AGENTOS_CONTINUITY_MIRROR_BRANCH=main
AGENTOS_CONTINUITY_MIRROR_ROOT=projects
AGENTOS_CONTINUITY_MIRROR_TOKEN=<private repo contents read/write token>
```

The token is used only by the Core gateway. IDE clients do not need it.

The default checkpoint path for `agentmanager` is:

```text
projects/agentmanager/continuity/latest.json
```

Project ids containing path-unsafe characters are encoded into a filesystem-safe slug rather than interpolated directly into a repository path.

## Update behavior

The mirror publishes after successful Control Plane `submit` and `complete` operations.

- unchanged snapshots do not create another commit
- GitHub optimistic-concurrency conflicts are re-read and retried once
- network/GitHub failures return mirror status `degraded`
- mirror failure never rolls back or fails the Control Plane task operation

The mirror timeout is bounded; it is not the execution fence. Task lease/idempotency remain in the Control Plane.

## Privacy boundary

The mirror contains the current Canonical IR and a compact task summary. It never includes:

- Control Plane bearer token
- GitHub mirror token
- Provider API keys
- Provider Bridge wake token

However, anything intentionally placed inside Canonical IR will also be mirrored. In particular, `agentos ask --include-diff` may place source-code diff text into Canonical IR. The target repository therefore must remain private and access-controlled.

## ChatGPT continuation convention

For a GitHub-connected ChatGPT session, the project continuation procedure is:

1. Read `projects/<project-id>/continuity/latest.json` from the private Data Layer repository.
2. Verify `protocol` and `current_ir_digest`.
3. Treat `canonical_ir` as the latest shared continuation state.
4. Inspect `latest_task.status` / `recommended_action` before creating new work.
5. Read the logic repository/branch referenced by the task context when code details are needed.
6. Do not overwrite the private mirror manually during normal operation; let the Control Plane publish it.

This lets a user return to ChatGPT and say **“continue”** without copying an IR capsule from another IDE. It still does not give AgentOS the ability to proactively inject a message into an already-open ChatGPT browser conversation; that remains a platform ingress boundary.

## Legacy handoff capsule

`projects/<project-id>/handoff_capsule.md` remains useful for humans and tools that only accept pasted text. It is not the machine continuity authority once `continuity/latest.json` is enabled.
