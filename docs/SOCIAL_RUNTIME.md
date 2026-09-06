# AgentOS Shared Social Runtime

Issue: #267. This runtime activates the generic social capability extracted by #154 without granting broad social-write authority.

## Boundary

The runtime is a Core-owned service around `agentos_node.social`; product repositories do not import provider adapters, store Threads App Secret/access tokens, or exchange OAuth codes themselves.

Default bind: `127.0.0.1:8771`. The accepted public product boundary is `https://studio.milkcat.org/dashboard/api/social`, backed by a strict Next.js allowlist to the fixed local upstream. It is not a generic proxy: the internal acceptance endpoint and control token are never exposed publicly.

The service itself accepts only fixed JSON contracts and never arbitrary provider URLs, HTTP methods, commands, argv, or secret retrieval.

### Product API

- `GET /healthz`: reports service and provider configured/unconfigured booleans only.
- `POST /v1/social/status`
- `POST /v1/social/connect`
- `GET /v1/social/oauth/threads/callback`
- `POST /v1/social/disconnect`
- `POST /v1/social/publish`
- `POST /v1/social/reply`

Product calls require an exact registered `product_id` plus `X-AgentOS-Product-Key`. Registration is runtime configuration, not repository data.

`connect` creates a runtime-owned OAuth state and an HttpOnly/Secure/SameSite=Lax browser-session cookie. The public gateway rewrites only that callback cookie path from the runtime-local callback path to the fixed public callback path. The provider callback must match both the single-use OAuth state and the original browser-session cookie. On success the browser is redirected only to the pre-registered product return base plus the previously validated relative `return_to` route. The return contains only connection/binding information; provider authorization code/token material stays server-side.

### Runtime control API

- `POST /internal/v1/social/acceptances`

This route requires `X-AgentOS-Control-Token`, is deliberately separate from product authentication, and is not exposed through the public social gateway. It issues a process-local one-shot acceptance for exactly one:

- product
- platform
- operation
- account binding
- `write_intent_id`

A credential/account binding never creates publish authority. Product credentials cannot mint write acceptance. The acceptance is consumed before provider execution; mismatch also consumes it and fails closed.

## Runtime-owned secret configuration

No secret values belong in Git.

- `AGENTOS_THREADS_APP_ID`
- `AGENTOS_THREADS_APP_SECRET`
- `AGENTOS_SOCIAL_CONTROL_TOKEN`
- `AGENTOS_SOCIAL_PRODUCTS_JSON`

The Threads redirect URI is a non-secret shared Core contract and is fixed to:

`https://studio.milkcat.org/dashboard/api/social/v1/social/oauth/threads/callback`

The Oracle host-local `AGENTOS_THREADS_REDIRECT_URI` entry is hydrated to that value only when it is missing or empty. A different non-empty operator value fails closed and is never overwritten or printed by the rollout.

`AGENTOS_SOCIAL_PRODUCTS_JSON` maps product IDs to a runtime API key and a fixed return base, for example structurally (values omitted):

```json
{
  "leopardcat-tarot": {
    "api_key": "<runtime-secret>",
    "return_base": "https://<product-host>"
  }
}
```

The provider config is shared by default. #267 does not create a LeopardCat-specific Meta App. If Meta policy later requires per-product applications, that must be introduced as an explicit provider-policy boundary rather than silently copied into product repos.

## Credential storage

The runtime persists account binding metadata and access tokens in its private runtime credential file, mode `0600`. Products receive only the non-secret binding ID/provider account identity. Receipts remain subject to the recursive secret guard from #154.

## Deployment and current evidence

```bash
python -m agentos_node.social.runtime_http --host 127.0.0.1 --port 8771
```

The Oracle persistent runtime and public gateway have live rollout evidence. The service remains valid while Threads is unconfigured; `/healthz` reports `threads.configured=false` and OAuth connect fails closed. This permits the Core-owned runtime, public route, and canonical callback URI to be deployed before the shared Meta App ID/Secret are provisioned.

## LeopardCat proving sequence

1. Deploy this shared runtime from `core/integration`.
2. Keep the fixed shared Threads callback registered as `https://studio.milkcat.org/dashboard/api/social/v1/social/oauth/threads/callback`.
3. Register `leopardcat-tarot` as a runtime consumer without creating a product-local Meta App.
4. Install shared Meta App ID/Secret in the host-local runtime secret boundary when available.
5. Verify public `/healthz` changes to `threads.configured=true` without exposing provider values.
6. Complete a real Threads OAuth callback and capture only sanitized account binding evidence.
7. Issue one exact write acceptance from the AgentOS control plane for a user-click-generated `write_intent_id`.
8. Publish `primary_text` plus optional typed `text_attachment` through the runtime and retain only the secret-free receipt/permalink/object id.
9. Then integrate LeopardCat #65 against the accepted endpoint; its existing production fallback remains valid until that live proof exists.

A live provider receipt is required before #267 can be closed. Unit/hosted CI proves the boundary and fail-closed behavior, not Meta availability or credentials.
