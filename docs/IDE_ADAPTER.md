# AgentOS IDE Adapter

The IDE Adapter is the thin client layer for Distributed AgentOS. It lets VS Code, Cursor, Antigravity, JetBrains IDEs, SSH terminals, CI jobs, and other development environments share the same Canonical IR continuity state without installing the full AgentOS Host.

## Core rule

**IDE chat/session state is not the continuity authority. The Control Plane project state is.**

Every IDE should resolve the same `project_id`, read `/v1/projects/{project_id}/state`, and submit/continue Canonical IR through the Control Plane.

## Install

From this repository:

```bash
python -m pip install -e .
```

This installs two commands:

```text
agentos       # cross-IDE Distributed AgentOS client
agentos-node  # lightweight runtime-node client
```

Python 3.10+ is required.

## Client environment

```bash
export AGENTOS_CONTROL_PLANE_URL=https://agentos.example.com
export AGENTOS_CONTROL_PLANE_TOKEN=replace_with_authorized_client_token
```

For Windows PowerShell:

```powershell
$env:AGENTOS_CONTROL_PLANE_URL = "https://agentos.example.com"
$env:AGENTOS_CONTROL_PLANE_TOKEN = "replace_with_authorized_client_token"
```

Do not commit the bearer token.

## Stable project identity

The same project may be cloned under different folder names on different devices. Pin a stable project id once:

```bash
agentos init agentmanager
```

This creates the non-secret, commit-safe marker:

```json
{
  "project_id": "agentmanager",
  "schema": "agentos.project/v1"
}
```

at `.agentos/project.json`.

Project id resolution order is:

1. explicit `--project`
2. `AGENTOS_PROJECT_ID`
3. `.agentos/project.json`
4. workspace directory name

## Commands

### Read shared state

```bash
agentos status
agentos ir
```

`status` returns Control Plane health, current workspace metadata, and the current durable project state.

### Start new work

```bash
agentos ask "implement the next task" --capability code.implement
```

By default the IDE Adapter sends only lightweight workspace metadata. Source content and git diff are not included unless explicitly requested.

To include the current unstaged diff:

```bash
agentos ask "review my changes" --capability code.review --include-diff
```

The diff is bounded and marked when truncated.

### Continue from another IDE/agent

```bash
agentos continue
```

If a project task is already `submitted`, `leased`, or `running`, `continue` does **not** create a duplicate task. It returns the in-progress task instead.

If the latest task has a trusted continuation IR, `continue` submits that continuation. An optional new instruction creates a new handoff linked to the current IR:

```bash
agentos continue "now verify the implementation"
```

### Prefer a provider

```bash
agentos delegate gemini "review this implementation" --capability code.review
agentos delegate codex "implement the accepted review" --capability code.implement
```

The provider name is a Provider Registry id. It is a preference, not a bypass: the provider must be registered for the requested capability.

### Wait / inspect results

```bash
agentos wait <task-id>
agentos result <task-id>
agentos result
```

Without a task id, `result` resolves the latest Distributed AgentOS task for the current project.

## IDE agent operating pattern

An IDE agent that can invoke terminal commands should use this sequence:

```text
1. agentos status
2. If recommendedAction=wait:
      inspect/wait on the current task; do not fork duplicate work.
3. If a currentIR exists and the user says "continue":
      agentos continue [optional instruction]
4. For a genuinely new goal:
      agentos ask ...
5. For cross-model delegation:
      agentos delegate <provider> ...
```

This makes the word `continue` project-scoped rather than conversation-scoped.

## Workspace privacy boundary

Default Canonical IR workspace context includes:

- workspace name
- detected IDE type
- git repository yes/no
- branch
- commit
- dirty flag
- bounded changed-file list

It does **not** include the absolute workspace path or source-file contents. `--include-diff` is explicit opt-in because diffs may contain sensitive code or data.

## Control Plane API used by IDE clients

```text
GET  /health
GET  /v1/projects/{project_id}/state
GET  /v1/tasks/{task_id}
POST /v1/ir/submit
```

Runtime execution still uses the existing lease/complete endpoints. The IDE client does not need SQLite or `agent_core`.

## What this does not do

The CLI shares AgentOS state between IDEs and provider runtimes. It cannot directly inject a message into a particular already-open ChatGPT/Gemini browser conversation unless that product/session exposes an authorized inbound bridge. Browser-session continuation therefore uses the Provider Bridge relay mechanism described in `docs/PROVIDER_BRIDGE.md`.
