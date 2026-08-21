# Web Agent Adapter

## Boundary

A browser/web-hosted model is treated as another capability runtime, not as the owner of AgentOS state. The adapter gives it a Canonical IR request and accepts a small semantic response.

The web model is deliberately **not** allowed to construct `continuation_ir`. It may return:

- `result`
- `next_capability`
- `auto_continue`
- optional non-authoritative `continuation` metadata

`WebAgentAdapter` verifies `runtime_id`, `input_ir_id`, and `input_digest`, then uses the trusted Runtime Core to create the continuation lineage.

This prevents a web model from silently changing `project_id`, forging `parent_ir_id`, resetting `hop_count`, or bypassing the Control Plane continuation guard.

## Request protocol

`agentos.web-agent-request/v1`

The envelope contains:

- immutable `canonical_ir`
- `input_ir_id`
- `input_digest`
- target `runtime_id`
- an explicit response contract

## Response protocol

`agentos.web-agent-result/v1`

Required fields:

- `protocol`
- `runtime_id`
- `input_ir_id`
- `input_digest`
- `status`
- `result`

Optional fields:

- `next_capability`
- `auto_continue`
- `continuation`

A future ChatGPT/Gemini/browser automation bridge only needs to transport these envelopes. It does not need to understand AgentOS persistence or fabricate handoff state.

## CLI bridge

```bash
python3 scripts/web_agent_adapter.py export \
  --input current-ir.json \
  --runtime-id chatgpt-web \
  --output request.json

python3 scripts/web_agent_adapter.py complete \
  --input current-ir.json \
  --response web-response.json \
  --runtime-id chatgpt-web \
  --output runtime-result.json
```

The remaining automation problem is transport-specific: browser extension, Playwright bridge, vendor API, or another authorized connector can carry `request.json` to the web agent and return the constrained response.
