# ChatGPT MCP Deployment

## Current product constraint

As of 2026-08-27, OpenAI documents read/fetch MCP connections in ChatGPT developer mode for Pro users; full MCP is available to Business, Enterprise and Edu. Plus is not listed for custom MCP developer-mode connections. Treat this as a product-surface constraint, not an AgentOS limitation.

## AgentOS side

Install the optional MCP dependency set:

```bash
cd ~/agentmanager
git checkout feature/chatgpt-web-node
python3 -m pip install -r requirements-mcp.txt
```

Run the MCP bridge against the existing Control Plane:

```bash
export AGENTOS_CONTROL_PLANE_URL='https://studio.milkcat.org/dashboard/api/agentos'
export AGENTOS_CONTROL_PLANE_TOKEN='REDACTED_SCOPED_TOKEN'
export AGENTOS_CHATGPT_RUNTIME_ID='chatgpt-web'
export AGENTOS_MCP_HOST='127.0.0.1'
export AGENTOS_MCP_PORT='8000'
export AGENTOS_MCP_PATH='/mcp'
python3 scripts/agentos_mcp_server.py
```

Expected local endpoint:

```text
http://127.0.0.1:8000/mcp
```

Keep this loopback-only unless a separately authenticated reverse proxy is intentionally configured. Prefer OpenAI Secure MCP Tunnel for private/on-prem deployment.

## Exposed read tools

- `agentos_resume(project_id)` — authoritative resume packet: session, canonical IR, digest, execution context, latest task, recommended action.
- `agentos_project_state(project_id)` — durable current project state.
- `agentos_task(task_id)` — task status/readback.

The MCP server is not a second persistence layer. AgentOS Control Plane remains authoritative.

## ChatGPT continuity acceptance test

Use the real 3D Layout project, not a synthetic demo.

1. Ensure the AgentOS project state contains the existing `layoutlib`, demo URL/workspace, branch/commit as applicable, last verified action and next action.
2. Start Chat A with the AgentOS MCP app connected and resume the project.
3. Do at least one meaningful implementation step and checkpoint it through the normal AgentOS path.
4. Abandon Chat A.
5. Start Chat B without relying on ChatGPT-native history.
6. Ask `繼續 3D Layout`.
7. Chat B must call `agentos_resume` before reconstructing the task from semantic memory.
8. Pass only if Chat B identifies the existing implementation and exact next action instead of proposing a new generic 2D-to-3D architecture.

## What this does not solve yet

MCP tool availability is not itself a deterministic conversation prehook. Tool instructions strongly bias the model toward `agentos_resume`, but the platform may still choose whether to call it. A later continuity-hardening layer must enforce continuation intent routing outside model discretion if ChatGPT does not provide a native conversation-start/pre-tool hook.
