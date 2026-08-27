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

The MCP process MUST NOT receive the ONE root bearer. ONE provisions a separate revocable client token with only the permissions required by the read-only ChatGPT node:

```text
project.read
task.read
```

Projects can be constrained at issuance time. The MCP process uses:

- `AGENTOS_CONTROL_PLANE_URL=http://127.0.0.1:8765` on the ONE host
- `AGENTOS_CHATGPT_CLIENT_TOKEN=<scoped agc_ token>`
- `AGENTOS_CHATGPT_PRINCIPAL_ID=<stable account integration principal>`
- `AGENTOS_CHATGPT_RUNTIME_ID=chatgpt-web`

No ONE bearer credential or canonical state is stored on client devices.

## Provision on ONE

Issue a ChatGPT Cloud principal on the ONE host:

```bash
python3 scripts/provision_chatgpt_cloud_principal.py \
  --db "$AGENTOS_CONTROL_PLANE_DB" \
  --principal-id '<stable-principal>' \
  --project layout-3d
```

Store the returned `agc_...` token in the ONE secrets file as `AGENTOS_CHATGPT_CLIENT_TOKEN` and set `AGENTOS_CHATGPT_PRINCIPAL_ID` to the same stable principal. Then install the cloud service:

```bash
pip install -r requirements-mcp.txt
bash scripts/install_chatgpt_cloud_node.sh
```

The service runs as `agentos-chatgpt-mcp.service`, binds only to loopback by default, and talks to ONE at `127.0.0.1:8765`. A reverse proxy / secure public ingress can expose the MCP path without exposing the Control Plane directly.

## Current ChatGPT product gate

As of 2026-08-27, OpenAI documents remote custom MCP in ChatGPT Developer Mode for Pro read/fetch use, with full MCP currently available to Business and Enterprise/Edu. A Plus account therefore cannot yet complete the native account-scoped attachment through arbitrary custom MCP.

The intended Plus path is a reviewed/published ChatGPT App/Plugin backed by this same remote MCP endpoint. This is a product-distribution gate, not an AgentOS architectural dependency. The browser extension + localhost companion remains a fallback/debug transport and is not the definition of a completed ChatGPT Cloud Node.

## Continuity Floor

Once the ChatGPT account can connect the remote app/MCP, acceptance is device-independent:

1. ChatGPT on device A resumes the existing 3D Layout project.
2. ONE returns canonical state containing the existing `layoutlib`, demo/deployment identity, current revision, last verified result and next action.
3. Open ChatGPT on device B or mobile using the same account.
4. Start a fresh conversation and request continuation.
5. ChatGPT calls `agentos_resume` and recovers the same operational state.
6. No local extension, localhost service, copied prompt or previous conversation history is required.

A generic 2D-to-3D redesign is a regression failure.
