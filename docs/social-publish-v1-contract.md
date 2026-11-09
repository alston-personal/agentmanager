# AgentOS social.publish v1 — execution contract (proposal)

Status: implementation in progress; not deployed or authorized for automatic publishing.

## Existing verified transport
GitHub Actions -> Oracle self-hosted runner -> Bootstrap Control -> Social Runtime -> Threads. Preserve the current credential binding and existing Day 1/Day 2 published receipts. Do not replay old publish requests.

## Required command
A single fixed action `agentos.social_threads_mio_approved.publish` takes only an immutable source_commit (40 lowercase hex) and an approved post_key matching `mio-post-[a-z0-9-]{1,72}`. The post body is never accepted from issue comments, arbitrary workflow inputs, or untrusted shell variables. Fetch `personas/mio/approved/<post_key>.txt` from the exact commit, and verify the expected account is `sunlake.milkcat`.

## Preconditions and idempotency
Check account binding, canonical post receipt, local per-key lock, and a successful Threads read before issuing acceptance. Unknown read result must fail closed. Persist PUBLISHING before the provider call and treat timeout/ambiguous response as VERIFY_REQUIRED, not safe-to-retry. Reconcile against provider id/permalink before retrying. A per-key receipt should contain post_key, content hash, account binding, provider ID, permalink, acceptance/request IDs, source commit, outcome and timestamps. Never expose tokens in logs or receipts.

## Completion
Only provider object ID + canonical permalink + success receipt means PUBLISHED. Duplicate invocations must resolve to exactly the same provider ID. Save receipt in canonical Persona IR and expose execution evidence to the caller.

## Rollout gates
1. Tests for malformed key, wrong account, duplicate/concurrent jobs, read failure, publish timeout and crash after provider success.
2. Pin and review the authorized post content and source commit.
3. Use explicit, audited invocation rather than automatic deployment-side social writes; decouple publisher and deploy workflows.
4. One controlled live post, verified readback and canonical IR receipt.
