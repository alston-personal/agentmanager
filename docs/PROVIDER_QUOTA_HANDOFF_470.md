# #470 — abrupt provider quota exhaustion: model-free recovery slice

**Status:** implementation candidate, NOT deployed, NOT end-to-end verified. Reuse `scripts/work_completion.py`; do not introduce another queue, supervisor or parallel task authority.

## Problem

A provider (e.g., Gemini on Oracle) can stop without a final assistant message. The model cannot be trusted to save a last-minute handoff. Local runtime processes, Git worktrees, command outcomes, and durable task state must remain accessible independently of that model.

## New bounded functions

- `recover_provider_failure(path, work_id, actor, failed_owner, expected_generation, failure_receipt, failure_reason, next_action)`: within the existing locked work ledger, perform compare-and-swap of owner/generation and transfer to the Completion Controller. Record the runtime-observed receipt ID, increase generation, preserve the work item, and set `blocked/provider_capacity_recovery_pending_reconciliation`. **No unknown operation is replayed** and the task is not incorrectly marked done.
- `assert_execution_fence(path, work_id, owner, generation)`: cooperating runtime adapters can use it before side effects to reject stale or expired leases.

The functions are model-free; they use local Python and durable storage only. Classification deliberately reuses existing `classify_blocker`, not a new provider exception subsystem.

**Trust boundary:** `actor` is a string in this Python API, NOT identity authentication. Only an authenticated Runtime/ONE entrypoint can validate the actual failure receipt and invoke recovery. Do not expose this function as an untrusted HTTP endpoint, CLI command or allow a web model to self-assert that it is the Completion Controller. Checking the local ledger before a write is NOT sufficient against bypass or time-of-check/time-of-use races. GitHub writes and Oracle tool execution require authoritative generation fencing at their own mutation boundary (or an equivalent scoped credential/branch-protection enforcement). Existing direct GitHub connector writes are **not yet** fenced by this change.

## Required runtime sequence

1. Runtime persists task ID, executor identity, owner generation, target branch/ref, expected HEAD SHA, worktree-dirty status, operation ID, and intent **before** tool invocation; append immutable outcome receipt afterwards.
2. When a provider fails, the runtime (not the failed model) classifies actual error and issues a trusted runtime receipt. A 429 alone is ambiguous; distinguish throttling, exhausted quota, OAuth, transport and HTTP 5xx.
3. An authenticated Completion Controller reads observed generation and calls `recover_provider_failure`; stale or duplicate recovery fails closed.
4. Controller inventories *in-flight/unknown* side effects using their idempotency keys, Git remote/local SHA, pending PRs, dirty worktree, and execution receipts; do not blind-retry or reset.
5. Only after reconciliation may the Controller authorize a new executor Lease and dispatch work. The new executor reads latest IR, writes to the existing canonical task branch, and must present the current fenced generation at each effectful boundary.
6. Model-free operations (Git read, state inspection, tests, receipts) remain possible when a model has no credits, provided Oracle Runtime, connectivity and credentials are healthy. No promise that the exhausted Gemini model itself can continue generating.

## Explicit remaining blockers to full acceptance

- Wire trusted runtime provider-failure classification/receipt and recovery call into the actual Oracle executor host; this change alone does not automatically detect exhausted Gemini quotas.
- Implement authoritative write-path fencing on **all** executor/relay/GitHub paths, including direct GitHub connector writes and in-flight actions; `assert_execution_fence` alone is only a cooperation check.
- Ensure write-ahead intent and operation outcome journal durability across abrupt death, with unknown-outcome reconciliation.
- Validate Oracle local worktree SHA, remote SHA, deployed SHA, and dirty state without resetting or pushing in-flight changes.
- Run Gemini → ChatGPT Web → Gemini abrupt-failure simulation, stale-executor rejection, no-duplicate-side-effect verification and obtain an Oracle `agentos.execution-receipt/v1`.

## Safety

Do not merge to protected `main` without explicit authorization. Do not claim this code is installed on Oracle or that fallback can already read Oracle Local. This is a focused #470 change and should be reconciled against existing `core/integration` before deployment.
