# AgentOS Social Capability Pack v0.1

## Purpose

Move reusable social publishing/retrieval out of product repositories such as Zeus Writer.
Products express intent; AgentOS owns credentials, platform adapters, governance and receipts.

## Capability surface

| Capability | Risk | Default policy | Notes |
| --- | --- | --- | --- |
| `social.threads.identity.read` | low | allow | Credential health / account identity only |
| `social.threads.post.read` | low | allow | Subject to API visibility and token permissions |
| `social.threads.replies.read` | low | allow | Evidence retrieval; never implies arbitrary public-post access |
| `social.threads.publish` | medium | explicit write intent | `agentos-social` requires `--allow-write` |
| `social.threads.reply` | medium | explicit write intent | `agentos-social` requires `--allow-write` |
| `social.threads.delete` | high | deny in v0.1 | Not implemented |

Facebook and Instagram use the same contract in the next adapter increment; they must not be
re-embedded into Zeus Writer.

## Credential boundary

Callers refer to logical credentials (`threads/default`). The executor maps that ref to a local
environment/secret binding (`SOC_THREADS_TOKEN`). A secret value must never be written into a
receipt, Git commit, task payload, evidence file or caller response.

Bitwarden may continue provisioning the environment on the Oracle executor. That provisioning is
separate from capability invocation.

## Receipt contract

Every invocation emits `agentos.social-receipt/v0.1` containing capability, credential ref,
platform operation, timestamps, status and sanitized platform identifiers/results. It never
contains an access token.

## Threads API boundary

Publishing rights and public-reading rights are different. A token that successfully publishes to
its own account MUST NOT be treated as proof that it can retrieve an arbitrary third-party Threads
post or its reply tree. `post.read` / `replies.read` therefore return a failed receipt when Meta
rejects the object or permission instead of falling back to scraping inside the adapter.

A browser/public-web evidence adapter may be composed later when policy allows it; that is a
separate capability and provenance source.

## Product migration

### Zeus Writer

`feature/social-capability-client` uses `agentos-social` first. Its legacy direct Threads API path
remains only as a temporary migration fallback and can be disabled after the AgentOS executable is
installed and live receipts are verified.

### Vendor Reputation

Vendor ingestion should consume `social.threads.replies.read` receipts as raw evidence. It must not
automatically convert every reply into a rating. Entity extraction, sentiment/recommendation
classification, duplicate normalization and human review happen after evidence capture.

## Acceptance gates

1. Unit tests prove secret-free receipts and normalized read/write contracts.
2. Oracle identity health check returns only presence/validity/username, never the token.
3. Zeus Writer publishes one controlled test through AgentOS and receives a receipt.
4. Vendor ingestion attempts the supplied Threads source. If Meta denies third-party access, the
   result is recorded as an API boundary and the browser evidence path is used instead.
5. Only after shadow comparison succeeds is the direct Zeus Writer Threads API fallback removed.
