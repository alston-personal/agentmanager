# ChatGPT Cloud Node

## Definition of done

The authoritative ChatGPT AgentOS node is account/cloud scoped, not device scoped.

A valid implementation must continue the same AgentOS project from any device where the same ChatGPT account has access to the configured remote app/MCP integration. Chrome extensions, localhost companions, browser profiles and machine identifiers are optional fallback transports only.

## Preferred topology

```text
ChatGPT account
    -> remote ChatGPT App / MCP
    -> ONE Gateway
    -> AgentOS canonical state
```

Durable identity:

```text
executor_type = chatgpt-web
identity_scope = account
principal_id = stable integration principal
```

Ephemeral and non-authoritative:

```text
device
browser
conversation id
tab id
local extension state
```

## ONE contract

`agentos_resume(project_id)` calls the existing authenticated `/v1/attach` path. The attach metadata identifies the account-scoped ChatGPT principal and transport. ONE remains authoritative for canonical state, execution context, lineage and resume action.

The remote MCP process uses:

- `AGENTOS_CONTROL_PLANE_URL`
- `AGENTOS_CONTROL_PLANE_TOKEN`
- `AGENTOS_CHATGPT_PRINCIPAL_ID`
- `AGENTOS_CHATGPT_RUNTIME_ID=chatgpt-web`

No ONE bearer credential is stored on client devices.

## Current ChatGPT product gate

As of 2026-08-27, OpenAI documents remote custom MCP in ChatGPT Developer Mode for Pro read/fetch use, with full MCP currently available to Business and Enterprise/Edu. A Plus account therefore cannot yet complete the native account-scoped attachment through custom MCP.

This is a product-surface gate, not an AgentOS architectural dependency. The remote MCP/ONE contract is the primary implementation; the previously built browser extension + localhost companion remains a fallback/debug transport and is not the definition of a completed ChatGPT Cloud Node.

## Continuity Floor

Once the account can connect the remote MCP app, acceptance is device-independent:

1. ChatGPT on device A resumes the existing 3D Layout project.
2. ONE returns the canonical state containing the existing `layoutlib`, demo/deployment identity, current revision, last verified result and next action.
3. Open ChatGPT on device B or mobile using the same account.
4. Start a fresh conversation and request continuation.
5. ChatGPT calls `agentos_resume` and recovers the same operational state.
6. No local extension, localhost service, copied prompt or previous conversation history is required.

A generic 2D-to-3D redesign is a regression failure.
