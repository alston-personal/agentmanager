# Agent Provider Bridge

## Purpose

The Provider Bridge removes the human clipboard from cross-agent continuation.
It is a lightweight runtime that receives a Dispatcher wake-up, leases the exact
Control Plane task, invokes the provider selected for the task capability, wraps
the provider's semantic output through the trusted WebAgentAdapter, and completes
the task back to the Control Plane.

```text
Canonical IR
   -> Control Plane task
   -> Runtime Dispatcher
   -> Provider Bridge wake
   -> exact task lease
   -> Provider Registry
        |- OpenAI Responses
        |- OpenAI-compatible Chat / LiteLLM
        |- Gemini generateContent
        `- authorized browser/custom relay
   -> semantic result only
   -> trusted WebAgentAdapter
   -> verified Runtime Result
   -> Control Plane complete
   -> Continuation IR / next dispatch
```

The provider never owns AgentOS lineage. It cannot choose `runtime_id`,
`input_ir_id`, input digest, `parent_ir_id`, or hop count. Reserved continuation
metadata (`completed_by`, `previous_capability`, `ready_for_next_agent`,
`auto_continue`, `next_capability`) is also protected by the adapter.

## Exact push lease

A push wake is bound to `task_id`. The Bridge calls:

```text
POST /v1/tasks/{task_id}/lease
```

instead of generic `lease next`. This prevents a wake for task A from stealing
task B when several tasks target the same runtime.

If the Bridge dies after leasing, the lease expires. Pull-node leases release
their target so another node may take over. A durable push target registered by
the Runtime Dispatcher keeps its target and becomes wakeable again after the
stale-dispatch timeout.

## Provider routes

Provider route files are intentionally non-secret. See:

`config/provider-routes.example.json`

Supported provider kinds:

- `openai_responses` — OpenAI Responses API (`/v1/responses`)
- `openai_chat` — OpenAI-compatible `/chat/completions` endpoints, including LiteLLM-style proxies
- `gemini_generate_content` — Gemini `models.generateContent` with JSON MIME response mode
- `relay_webhook` — an authorized browser extension, desktop bridge, or custom vendor adapter

Each route specifies an `api_key_env` or `token_env` name. The credential itself
stays in the environment/secrets store and is never persisted in the route file.

Example capability sequence:

```text
ai.reason      -> openai-reasoner
ai.verify      -> gemini-verifier
code.implement -> codex-coder
web.chatgpt    -> chatgpt-browser-relay
```

The IR can select a provider among providers that advertise the same capability:

```json
{
  "context": {
    "provider_policy": {
      "preferred_provider": "gemini-verifier",
      "deny_providers": ["provider-under-maintenance"]
    }
  }
}
```

Provider policy never bypasses capability registration.

## Core configuration

The Control Plane/Dispatcher only needs to know the Provider Bridge as one push
runtime. The Bridge performs the provider-level routing internally.

```bash
export AGENTOS_CONTROL_PLANE_PUBLIC_URL=https://agentos.example.com
export AGENTOS_CONTROL_PLANE_TOKEN='...'
export AGENTOS_PROVIDER_BRIDGE_ENDPOINT=https://provider-bridge.example.com/v1/runtime-dispatch
export AGENTOS_PROVIDER_BRIDGE_TOKEN='...'
export AGENTOS_PROVIDER_RUNTIME_ID=provider-bridge
export AGENTOS_PROVIDER_CAPABILITIES=ai.reason,ai.synthesize,ai.verify,ai.research,code.implement,code.review,web.chatgpt

python3 scripts/distributed_gateway.py
```

For a Bridge on the same host, loopback HTTP is allowed:

```bash
AGENTOS_PROVIDER_BRIDGE_ENDPOINT=http://127.0.0.1:8775/v1/runtime-dispatch
```

Non-loopback Provider Bridge endpoints require HTTPS.

## Provider Bridge configuration

```bash
export AGENTOS_PROVIDER_RUNTIME_ID=provider-bridge
export AGENTOS_PROVIDER_BRIDGE_TOKEN='...'
export AGENTOS_CONTROL_PLANE_TOKEN='...'
export AGENTOS_PROVIDER_ROUTES_FILE=config/provider-routes.example.json

# Provider secrets referenced by the route file
export OPENAI_API_KEY='...'
export GEMINI_API_KEY='...'
export AI_API_ACADEMIA_KEY='...'
export CHATGPT_RELAY_TOKEN='...'

python3 scripts/provider_bridge.py --host 127.0.0.1 --port 8775
```

The Bridge returns HTTP 202 immediately for wake-ups and runs provider calls in a
bounded worker pool. Durable reliability does not depend on that HTTP connection:
the Control Plane lease/result state remains authoritative.

## ChatGPT web versus OpenAI API

An OpenAI API model is a provider runtime, but it is not the same thing as an
existing interactive ChatGPT browser conversation. To continue a specific web
session, use `relay_webhook` with an authorized browser/desktop bridge that knows
how to deliver the Provider Request envelope to that session and return semantic
JSON. AgentOS still owns the task lease and continuation lineage.

The same relay mechanism can wrap other web-only agents without changing the
Control Plane or Canonical IR.

## Failure semantics

Provider/network/parsing failures complete the leased task as `failed` with a
`provider_failed` result. A provider cannot fabricate a success continuation by
returning malformed metadata. Duplicate wakes are harmless because exact task
lease is atomic; only one worker can own the task.

## Security boundary

- Control Plane: bearer-authenticated; public exposure should be HTTPS.
- Provider Bridge wake endpoint: bearer-authenticated for non-loopback binds.
- Provider credentials: environment/secrets store only.
- Route registry: non-secret metadata only.
- Browser/custom relay: HTTPS outside loopback and optional bearer token.
- Model output: untrusted semantic JSON until WebAgentAdapter validates it.
- Execution: capability-gated; no generic remote shell is introduced.
