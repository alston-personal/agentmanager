# ChatGPT Web Node -> ONE

## Status

This is the ChatGPT Plus-compatible AgentOS node path. It does not rely on ChatGPT conversation memory and does not require custom MCP availability.

```text
ChatGPT Web content script
  -> continuation intent gate
  -> local companion http://127.0.0.1:8766/v1/resume
  -> AgentOS ONE /v1/attach
  -> Canonical IR + compiled execution context
  -> deterministic continuation prompt
  -> ChatGPT executor
```

The browser extension stores routing metadata only (`conversation -> project_id`, `activeProjectId`, companion transport token). Canonical state and the ONE credential stay outside the browser.

## Windows install

From a checkout containing this feature:

```powershell
$env:AGENTOS_CONTROL_PLANE_TOKEN = '<authorized ONE token>'
Set-ExecutionPolicy -Scope Process Bypass
.\scripts\install_chatgpt_node_windows.ps1
```

The installer defaults ONE to:

```text
https://studio.milkcat.org/dashboard/api/agentos
```

It installs the Python package, creates a random localhost companion token, sets user environment variables and adds a per-user Startup launcher for the companion.

Then load this folder as an unpacked Chrome/Edge extension:

```text
browser/chatgpt-agentos-node
```

Paste the companion token printed by the installer into the extension popup. Bind the current ChatGPT conversation to its stable AgentOS `project_id` once. The latest bound project is also retained as the rollover fallback for a fresh conversation.

## Continuation protocol

The content script intercepts these intents before ChatGPT receives them:

- `繼續`
- `繼續完成`
- `continue`
- `resume`
- `/goal <project-id> [intent]`

For an intercepted continuation, the original message is not submitted. The extension first calls the local companion. The companion must obtain a ONE attachment and return a prompt bound to `current_ir_digest`. Only then is the composer replaced with the authoritative continuation prompt.

If ONE/companion/token/project routing fails, the operation fails closed and ChatGPT is not allowed to guess from conversational memory.

## Conversation rollover

A bound conversation stores only its routing association. When ChatGPT reaches a conversation limit and a fresh chat is opened, `activeProjectId` provides the default project routing for an explicit continuation intent. `/goal <project-id>` can deterministically rebind when switching projects.

## Continuity Floor acceptance

For the 3D Layout case:

1. Bind the existing 3D Layout AgentOS project.
2. Ensure ONE canonical state contains the real `layoutlib`/demo operational state, last verified result and next action.
3. Open a fresh ChatGPT conversation with no useful native chat history.
4. Enter `繼續`.
5. The extension must block direct submission, call ONE through the companion and inject an `agentos.chatgpt-browser-resume/v1` payload.
6. ChatGPT must resume the actual existing implementation. A generic 2D-to-3D architecture restart is a failure.

## Security boundary

- Companion binds loopback only.
- Companion token must be at least 24 characters.
- ONE credential is never stored in extension storage.
- Browser stores no Canonical IR.
- `current_ir_digest` is required before a continuation prompt is accepted.
- Failure to restore state is fail-closed.
