# AgentOS content.publish v1

Issue: #686

## Purpose

Provide one governed publishing surface for ZeusWriter, Mio, Oursong and other
AgentOS projects. Projects produce a Content Artifact; platform credentials,
sessions and transport details remain inside registered providers.

```text
Content Artifact
  -> content.publish / content.publish.batch
  -> provider registry + health snapshot
  -> transport resolver
  -> existing Social / platform capability
  -> independent receipt
  -> reverse-link / analytics
```

## Caller contract

```json
{
  "schema": "agentos.content-publish/v1",
  "project_id": "zeus-writer",
  "platform": "x",
  "account_ref": "oursong_alston",
  "content_ref": "artifact://chapter/1",
  "mode": "publish",
  "authority": "approved-content-publish",
  "write_intent_id": "..."
}
```

The caller may not provide API tokens, cookies, arbitrary shell, executables,
browser JavaScript, arbitrary endpoints, passwords/secrets, or arbitrary
filesystem paths.

## Content Artifact

```json
{
  "schema": "agentos.content-artifact/v1",
  "title": "...",
  "body": "...",
  "media": [],
  "link": "...",
  "hashtags": [],
  "reply": null,
  "metadata": {}
}
```

## Provider registry

The source manifest is `config/content_publish_providers.json`. Static registry
entries describe transports and capabilities only. Live health/auth state must be
supplied by health probes; do not equate node-online with publisher-ready.

The canonical lower layer for supported social platforms is the existing generic
Social Capability extracted by Core #154 and the shared Social Runtime activated
by Core #267. It already owns provider-neutral requests/receipts, credential vault
boundaries, account binding, exact one-shot write acceptance and the Oracle runtime
at 127.0.0.1:8771/public gateway. Mio is already a real consumer of this runtime.

`content.publish` is therefore a higher-level artifact/batch/provider-resolution
facade. It MUST delegate social execution to #154/#267 rather than duplicating
OAuth, tokens, account binding, acceptance or provider HTTP. Resolving a provider
does not mint authority: the Social Runtime's exact write acceptance remains
required for a social write.

## Account Registry and Social consumer isolation

Social Runtime bindings are scoped to an exact `product_id`; a Threads binding
created for `galaxy` is not valid for `content-publish`. ZeusWriter therefore
must not borrow Mio/Galaxy product credentials or account bindings.

The non-secret source configuration is
`config/content_publish_accounts.json`. It maps a stable caller-facing
`account_ref` to the expected platform/product identity and an allowlisted
bootstrap source. Runtime binding metadata is persisted only on the Oracle host
at `/home/ubuntu/.config/agentos/content-publish/accounts.json`; tokens remain in
the Social Runtime credential vault.

For the existing ZeusWriter Threads account, the fixed
`agentos.content.social.bootstrap` Ubuntu Action Relay action may migrate only
the pre-existing `SOC_THREADS_TOKEN` from the fixed legacy ZeusWriter env path.
It first resolves the token to a Threads identity, verifies the allowlisted
username, registers the `content-publish` Social Runtime consumer, stores a
product-specific binding in the shared vault, writes only secret-free Account
Registry metadata, and restarts the fixed Social Runtime service. It accepts no
caller token, path, product ID, endpoint, command, or shell.

Bootstrap performs a host-local credential migration, so its receipt states
`credential_migrated=true` when successful while separately proving
`public_publish_performed=false`. The read-only
`agentos.content.social.inspect` action verifies the resulting binding through
the normal Shared Social Runtime `identity.read` route. Authentication success
does not by itself prove Threads publish entitlement; that remains `UNKNOWN`
until a separately authorized write acceptance/E2E proves it.

## Resolution

1. Match platform and account.
2. Filter by content needs (media/reply/thread).
3. Prefer READY unattended provider.
4. If no unattended provider is READY but a governed assist provider is READY,
   return `HUMAN_CONFIRM_REQUIRED`.
5. If none are READY, surface the best provider health explicitly.
6. Never silently skip or substitute another platform.

X example:

```text
x-api READY
  -> x-api

x-api ENTITLEMENT_REQUIRED + x-web-assist READY
  -> x-web-assist
  -> HUMAN_CONFIRM_REQUIRED

both unavailable
  -> CAPABILITY_UNAVAILABLE
```

## X non-publish probe

`scripts/x_auth_inspect.py` checks credential presence and authenticated account
identity with GET `/2/users/me`. It does not create a Post or upload media.

Because X does not expose a universally reliable no-side-effect endpoint that
proves create-Post or media-upload entitlement for every auth/tier combination,
the probe reports write/media entitlement as `UNKNOWN` unless an authoritative
provider-side signal is available. A successful identity response proves
`authentication_status=READY`, but overall publish-provider status remains
`UNKNOWN` until write entitlement is proven. Live publish is not used as an
entitlement probe.

Legacy ZeusWriter credentials remain owned by the `ubuntu` runtime boundary.
The normal `agentos-node` runner must not read `/home/ubuntu/zeus-writer/.env`
directly. The fixed `agentos.content.x.auth.inspect` Action Relay action runs
under the existing ubuntu-owned deterministic relay, accepts only an optional
expected username, and returns a sanitized read-only receipt. No caller-selected
path, endpoint, token, shell, or browser script is accepted.

## Batch contract

`agentos.content-publish-batch/v1` contains one project/content reference and a
non-empty list of platform/account targets. Each target is validated through the
same single-publish contract, has its own `write_intent_id` and
`required | optional | best_effort` policy, and receives an independent receipt.

## Receipts / idempotency

Every successful or prepared operation returns a sanitized
`agentos.content-publish-receipt/v1`. Receipts include account_ref, provider,
status, content_hash and write_intent_id but never credentials.

The governed Threads write bridge persists a host-local intent ledger before
requesting Social Runtime write acceptance. Ledger identity is
`project_id + platform + account_ref + write_intent_id`; the exact payload is
bound by a request digest that includes `content_hash` and the public write
payload.

- a completed publish returns the stored receipt for subsequent identical intents;
- the same write intent with a different request digest is a conflict;
- failure before Social Runtime acceptance is explicitly `safe_to_retry=true`;
- once acceptance has been issued, any transport/provider ambiguity is persisted
  as `unknown` with `reconcile_required=true`, and a later capsule must not
  blind-retry it.

This keeps idempotency above one-shot Social Runtime acceptance: issuing a new
acceptance cannot accidentally duplicate a previously ambiguous write.

A provider must reconcile an UNKNOWN side effect before retrying the same
`write_intent_id + content_hash + platform + account_ref`. Blind retry after
timeout is forbidden.

## Governed Social write boundary

`agentos.content.social.write` is a fixed Ubuntu Action Relay action for the
first migrated live provider path: ZeusWriter -> Threads. It accepts only a
versioned typed request for the allowlisted `zeus-writer` project, `threads`
platform, registered `account_ref`, `publish|reply` operation, bounded text,
optional HTTPS image metadata, `write_intent_id`, 64-hex `content_hash`, and
the explicit `approved-content-publish` authority label. Token, cookie, path,
endpoint, product-id, shell and executable fields are not part of the contract.

The bridge resolves the host-local Account Registry, issues the exact existing
Social Runtime write acceptance using node-local control credentials, then
invokes the normal `/v1/social/publish|reply` endpoint with the product-specific
key. Provider/control credentials are never returned to the product caller.

The action being installed does **not** prove a platform account is write-ready.
Provider/account health and effect-level authority remain independent, and no
automatic live-write workflow is attached to this action.

Successful Threads writes perform a best-effort provider readback for
`permalink` after the provider object ID is known. A readback failure does not
downgrade the already successful write.

## Incremental migration

1. Land contract + resolver + registry.
2. Wire existing Social Runtime provider.
3. Wrap Blogger and Matters legacy providers.
4. Diagnose X API without publishing.
5. Add X web-assist prepare flow.
6. Move ZeusWriter orchestration to content.publish.
7. Move reverse-linking to the post-publish step.
