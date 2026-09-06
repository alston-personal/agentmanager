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
- `GET /v1/social/oauth/threads/start?ticket=<opaque-one-time-ticket>`
- `GET /v1/social/oauth/threads/callback`
- `POST /v1/social/disconnect`
- `POST /v1/social/publish`
- `POST /v1/social/reply`

Product server calls require an exact registered `product_id` plus `X-AgentOS-Product-Key`. Registration is runtime configuration, not repository data. The product key MUST remain server-side; it is never placed in browser JavaScript, a redirect URL, an OAuth state, a receipt, or a cookie.

`connect` is intentionally split across a backend leg and a browser leg. The authenticated product backend receives only a short-lived opaque `browser_start_url`; it does not receive the provider authorization URL, provider OAuth state, browser callback session, app credential, or token. The user's browser navigates to that one-time start URL on the shared gateway. Only there does the runtime consume the ticket, create the provider OAuth state, create the browser callback session, set an HttpOnly/Secure/SameSite=Lax callback cookie on the shared gateway origin, and redirect to Threads authorization.

This split prevents the cross-origin failure mode where a product backend receives `Set-Cookie` from the shared runtime but the end user's browser never stores it. It also avoids the unsafe alternative of exposing `X-AgentOS-Product-Key` to browser code.

The public gateway rewrites only the callback cookie path from the runtime-local callback path to the fixed public callback path. The provider callback must match both the single-use OAuth state and the original browser-session cookie. On success the browser is redirected only to the pre-registered product return base plus the previously validated relative `return_to` route. The return contains only connection/binding information; provider authorization code/token material stays server-side.

The browser handoff ticket is process-local, random, single-use, and short-lived (five minutes by default). Runtime restart or ticket replay fails closed. It contains no credential material and is useless after redemption.

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

The Oracle persistent runtime and public gateway have live rollout evidence. The configured-provider verification through the public gateway has passed with `threads.configured=true` while keeping the actual App ID/Secret values out of Core, GitHub logs, workflow inputs, artifacts, and receipts. This is configuration evidence only; it is not yet real-user OAuth or publish acceptance.

## LeopardCat proving sequence

1. Deploy this shared runtime from `core/integration`.
2. Keep the fixed shared Threads callback registered as `https://studio.milkcat.org/dashboard/api/social/v1/social/oauth/threads/callback`.
3. Register `leopardcat-tarot` as a runtime consumer without creating a product-local Meta App.
4. Verify public `/healthz` reports `threads.configured=true` without exposing provider values.
5. Have LeopardCat's backend call `POST /v1/social/connect` with its server-side product credential and redirect the user only to the returned opaque `browser_start_url`.
6. Complete a real Threads OAuth callback and capture only sanitized account binding evidence.
7. Issue one exact write acceptance from the AgentOS control plane for a user-click-generated `write_intent_id`.
8. Publish `primary_text` plus optional typed `text_attachment` through the runtime and retain only the secret-free receipt/permalink/object id.
9. Integrate LeopardCat #65 against the accepted endpoint; its anonymous `<=500` production fallback remains valid until the live proof succeeds.
10. Perform real iPhone acceptance before closing the product issue.

A live provider receipt is required before #267 can be closed. Unit/hosted CI and configured-provider checks prove the boundary and fail-closed behavior, not real user OAuth, account binding, Threads publication, or real-device UX.
