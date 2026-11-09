# AgentOS Generic Social Capability

Status: Core candidate for Issue #154. Integration target is `core/integration` only.

## Boundary

Core owns provider-neutral social request/receipt contracts, capability registration, product-scoped OAuth callback state, credential isolation, account binding, provider adapters, and write governance. Product repositories own their content policy, scheduling, qualification, patrol/calibration, UI confirmation, and business data flow.

No social credential value belongs in git, a product browser, a social receipt, or a product content record. The shared provider is stateless with respect to product question/answer/content data.

## Generic v1 request

`agentos.social-request/v1` identifies `product_id`, platform, operation, optional account binding, and explicit target account. `publish`/`reply` require an explicit `write_intent_id`, account binding, target provider account, and `primary_text`. `text_attachment`, when present, is typed as `{plaintext, optional link_attachment_url}`.

Write capability presence, OAuth connection, credential presence, or executor availability never grants write authority. `SocialWriteGate` requires a separate exact `RuntimeWriteAcceptance` scoped to product + platform + operation + account binding. All registered social writes start with `runtime_accepted=false`.

## OAuth and credentials

OAuth state is random, single-use, ten-minute by default, and bound to product + browser session + platform. Provider authorization code exchange is server-side. Product return routing contains only local route plus sanitized connection/binding state. Access tokens and app secrets live behind `CredentialVault`; the reference vault is process-memory only and intentionally disconnects on restart.

The Threads transport follows the LeopardCat teacher flow: authorization code -> access token -> best-effort long-lived token exchange -> public identity -> explicit account binding. It does not require a separate Meta App per product; the provider configuration is shared-runtime configuration unless provider policy later forces separation.

## Threads

Core provides two distinct read paths:

- `social.threads.public_post.read`: anonymous bounded HTTPS reader with strict Threads host/redirect validation.
- credentialed identity/post/replies contract: registered but must be routed through a runtime adapter before being considered accepted.

Threads publish uses official `media_type=TEXT`, `auto_publish_text=true`, bounded primary text (`<=500`) and optional JSON `text_attachment` with bounded `plaintext` (`<=10000`) and optional http/https link attachment. Core publishing remains unauthorized by this document and by Issue #154.

## Facebook / Instagram

The generic registry defines identity/read/publish/reply/disconnect primitives for Facebook and Instagram under the same governance model. No concrete write adapter is marked runtime-accepted in this extraction; unsupported invocation returns `provider_adapter_not_runtime_accepted` rather than guessing provider behavior.

## Consumer proof

Two independent products are represented through the same v1 contract in `tests/test_social_threads_capability.py`:

1. **LeopardCat Tarot** — teacher implementation provenance: `alston-personal/leopardcat-tarot@5088eaa94e9604643fc431c64bfb94a3020ad3a8`, `website/divination/threads_publishing.py`. The Core test reproduces its explicit target-account + primary text + `text_attachment` path without exposing token/code data. LeopardCat's anonymous `<=500` Threads intent fallback remains product-owned and is not removed by this extraction.
2. **Vendor Reputation Service** — current product-owned counterpart is `alston-personal/vendor-reputation-service:app/threads_reader.py`, which resolves public Threads sources and intentionally retains Vendor ingestion/qualification outside Core. The Core test sends Vendor and LeopardCat through the identical `social.threads.public_post.read` provider contract.

This is contract-level shared-capability evidence, not authorization to deploy credentials or publish from either product.

## Provenance / retirement

- Legacy PR #18: early monolithic generic social executor; semantics reconciled here, do not merge it.
- PR #125: later modular `agentos_node/social/*` plus Vendor-specific `vendor_ingest.py`; generic concepts were reconciled, Vendor ingestion is explicitly excluded, do not merge it wholesale.
- PR #262: public Threads URL reader source; safe URL/read semantics were incorporated into `agentos_node/social/public_threads.py`, but its `main` target is not the Core integration path.
- LeopardCat teacher commit `5088eaa94e9604643fc431c64bfb94a3020ad3a8`: OAuth/account/text-attachment semantics accounted for.

After the focused #154 PR is integrated to `core/integration`, #18/#125/#262 should be closed as superseded with provenance links; none should be merged to protected `main` as part of this issue.

## Acceptance mapping

1. #18/#125 reconciled: provenance above and focused modules/tests.
2. Focused current branch from `core/integration`: `core/issue-154-social-capability`.
3. Secret values excluded from repo/receipts: recursive receipt guard + credential vault tests.
4. Writes fail closed: exact runtime acceptance gate; registry defaults false.
5. Vendor counterpart: product-owned `app/threads_reader.py`; no Vendor ingest in Core.
6. Tests/evidence: `tests/test_social_capability_contract.py` and `tests/test_social_threads_capability.py` plus focused CI.
7. Integration target: `core/integration` only.
8. Legacy provenance accounted before retirement: this document.
9. Teacher extension: product-scoped OAuth return, binding/disconnect, text attachment, no product content persistence, secret-free receipt, dual-consumer contract proof, shared provider config boundary.
