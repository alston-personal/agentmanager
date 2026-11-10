# Execution Backpressure and Async Handoff

Status: planning / core capability proposal

## Goal

Prevent tool-heavy or externally blocked work from making an otherwise healthy conversation feel stalled. Context pressure and execution pressure are different failure classes and must not be conflated.

The core distinction is:

`conversation_pressure != execution_pressure`

A long conversation can still be responsive. A short conversation can stall if it performs repeated external polling, large tool reads, or waits synchronously on remote systems.

## Why this exists

A recent Threads Galaxy / AgentOS session showed repeated apparent timeout while doing dense GitHub and workflow operations. The same conversation became responsive again when the work shifted to architecture discussion and lighter tool usage. This demonstrates that conversation length alone is not a sufficient cause signal.

AgentOS therefore needs a second lifecycle controller in addition to Context Rotation:

- Context Rotation manages conversation quality, stale state, and continuity.
- Execution Backpressure manages tool pressure, remote latency, polling, retries, and asynchronous waiting.

## Signals

Track these independently from context-rotation signals:

- `tool_call_rate`: tool calls per interaction window.
- `same_provider_burst`: repeated calls to the same external provider.
- `polling_density`: repeated state checks for a condition that could be event-driven.
- `tool_payload_volume`: total tool output size and truncation frequency.
- `external_latency`: observed call duration by provider/action.
- `retry_count`: bounded retries for the same logical operation.
- `timeout_rate`: recent timed-out or cancelled operations.
- `remote_wait_state`: workflow/job remains queued or in-progress.
- `runner_contention`: remote executor unavailable, queued, or saturated.
- `fanout_width`: number of independent external operations in one turn.

No single metric should imply conversation rotation.

## State machine

```text
EXECUTION_NORMAL
  -> EXECUTION_PRESSURED
  -> ASYNC_HANDOFF_RECOMMENDED
  -> WAITING_EXTERNAL_EVENT
  -> RESUME_READY
  -> EXECUTION_NORMAL
```

The system may stay in the same conversation throughout this lifecycle.

## Decision policy

### Continue synchronously

Use synchronous execution when:

- the next tool result is expected quickly;
- no more than a small bounded number of checks is needed;
- progress depends immediately on the result;
- an event-driven callback is not available.

### Convert to async handoff

Prefer async handoff when any of the following holds:

- a remote workflow is queued/in-progress and completion time is not deterministic;
- repeated polling would add no new information;
- the provider can emit a completion event;
- a retry backoff window exceeds the useful interactive wait time;
- the user can continue other work while the external operation completes.

The preferred pattern is:

```text
start external work
 -> persist pending operation
 -> return control to user
 -> completion event reaches ONE / AgentOS
 -> Trigger Router marks continuation resume-ready
 -> background execution resumes or Human Attention Gateway notifies only if needed
```

## Pending operation contract

```json
{
  "schema": "agentos.pending-operation/v1",
  "operation_id": "op-...",
  "project_id": "...",
  "generation_id": "...",
  "provider": "github-actions",
  "operation_type": "workflow_run",
  "external_ref": {
    "repository": "...",
    "run_id": "..."
  },
  "started_at": "...",
  "expected_event": "workflow.completed",
  "resume_capability": "...",
  "retry_policy": {
    "mode": "event_first",
    "max_retries": 2,
    "fallback_poll_after_seconds": 900
  },
  "state": "waiting"
}
```

The contract must be secret-free and must not contain arbitrary executable commands.

## Async event mapping

Examples:

```text
github.workflow.completed
 -> resolve pending operation
 -> hydrate exact continuation
 -> run acceptance / next bounded capability

provider.rate_limit.reset
 -> resume deferred operation

runner.available
 -> dequeue next governed job

deployment.completed
 -> mark receipt
 -> notify only if project policy requests it

deployment.failed
 -> bounded auto-repair
 -> escalate only after repair policy is exhausted
```

## Interaction with Context Rotation

These systems are orthogonal.

### High context pressure, low execution pressure

Example: many obsolete branches, old probes, repeated rediscovery.

Action:

`PREPARE_HANDOFF -> ROTATE_RECOMMENDED`

### Low context pressure, high execution pressure

Example: a fresh conversation starts a 10-minute workflow and polls it repeatedly.

Action:

`ASYNC_HANDOFF_RECOMMENDED`, not conversation rotation.

### High context pressure, high execution pressure

Finalize continuation first, persist the pending operation, verify hydration, then rotate. The pending external event must target the new canonical generation rather than the obsolete chat thread.

## Polling budget

Polling should be treated as a bounded fallback, not the normal implementation pattern.

Initial defaults:

- no more than 2 immediate status checks after starting an external long-running operation;
- after that, persist pending state and prefer event-driven resume;
- fallback polling uses exponential/backoff timing outside the interactive conversation;
- identical provider/status responses should not be repeatedly projected into model context.

These defaults should later be tuned from telemetry.

## Result compaction

Large external results should be separated into:

- authoritative raw artifact/reference;
- compact accepted-state projection;
- model-visible delta only.

Do not repeatedly inject full workflow logs, large API payloads, or unchanged state into the active conversation.

Recommended result classes:

```text
RAW_EVIDENCE
ACCEPTED_STATE
DELTA
ERROR_CLASSIFICATION
RESUME_SIGNAL
```

## Human Attention behavior

Execution pressure itself is not a reason to notify the user.

Notify only when:

- human approval is required;
- bounded autonomous recovery failed;
- an explicitly requested completion alert is ready;
- the operation changed user-visible outcome materially.

Do not notify merely because a workflow took a long time.

## Telemetry

Track:

- synchronous tool latency p50/p95 by provider/action;
- poll calls avoided by async handoff;
- median number of status checks per long-running operation;
- timeout/cancellation rate;
- repeated identical-result rate;
- tool output truncation rate;
- async resume success rate;
- pending-operation orphan rate;
- average time from provider completion to AgentOS resume;
- percentage of high execution-pressure cases incorrectly causing conversation rotation.

## Acceptance criteria

1. Starting a long-running GitHub Actions workflow does not cause repeated interactive polling.
2. The operation is persisted as a pending operation with enough information to resume safely.
3. Completion can resume through ONE/Event Bus without relying on the original ChatGPT thread remaining open.
4. Duplicate completion events cause one logical resume action.
5. A fresh conversation can hydrate the pending operation if rotation occurred while it was waiting.
6. Tool-heavy execution pressure alone never forces Context Rotation.
7. Large unchanged tool payloads are compacted or referenced rather than repeatedly re-injected.
8. Human notification occurs only when policy says human attention is useful.

## Implementation roadmap

### Phase E1 — Execution Pressure Observer

Create `agent_core/execution_pressure.py` as a read-only observer.

Outputs:

```text
EXECUTION_NORMAL
EXECUTION_PRESSURED
ASYNC_HANDOFF_RECOMMENDED
```

with deterministic reason codes.

### Phase E2 — Pending Operation Store

Add `agentos.pending-operation/v1` persistence scoped to project/generation. It must support idempotent state transition and terminal receipts.

### Phase E3 — Async Handoff Coordinator

Translate long-running tool work into persisted pending operations. Stop synchronous polling when budget is exhausted.

### Phase E4 — Event-driven Resume

Integrate GitHub Actions completion first, then other providers through ONE Event Bus / Trigger Router.

### Phase E5 — Result Compaction

Project raw evidence to accepted state + delta and prevent duplicate large payload injection.

### Phase E6 — Telemetry tuning

Tune thresholds and polling budgets from actual production traces rather than fixed intuition.

## Integration with Issue #360

This capability complements `Context Rotation + ONE reverse trigger + Human Attention Gateway`.

The combined lifecycle becomes:

```text
Conversation lifecycle observer
          |
          +-- context quality degraded --> continuation finalizer / rotation
          |
          +-- execution pressure high ----> async handoff / pending operation
                                             |
                                             v
                                      ONE Event Bus
                                             |
                                      Trigger Router
                                             |
                         +-------------------+------------------+
                         |                                      |
                  background resume                       human attention
```

The key design rule is:

**Do not rotate a conversation to solve an execution-lane problem, and do not keep polling an external system to solve a continuation problem.**
