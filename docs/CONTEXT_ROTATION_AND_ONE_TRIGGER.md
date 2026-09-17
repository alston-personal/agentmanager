# Context Rotation, ONE Event Triggering, and Human Attention Gateway

Status: planning / core capability proposal

## Goal

Make long-running AgentOS work resilient across conversation boundaries and allow ONE to trigger useful work in the opposite direction without depending on a specific ChatGPT Web thread remaining open.

The system must treat a chat thread as a temporary interaction surface, not as the canonical execution or memory boundary.

## Problem statement

Today the dominant path is effectively:

`ChatGPT/Agent -> AgentOS -> ONE`

This creates two recurring failure modes:

1. Long conversations accumulate stale tool output, old branch/deploy state, and repeated discovery until continuation quality degrades.
2. ONE can receive state and receipts, but there is no unified reverse path for ONE-originated events to wake background work, request human attention, or prepare a clean continuation.

A robust design needs both lifecycle rotation and reverse event flow.

## Core principles

1. ONE remains canonical control/state authority where applicable; chat history is never canonical state.
2. Conversation rotation must be driven by quality/risk signals, not a hard token threshold alone.
3. Before recommending rotation, AgentOS must persist a lossless continuation envelope and verify that a fresh client can hydrate it.
4. ONE-triggered events must route through a governed event bus and policy engine; not every event should wake a model or notify a human.
5. ChatGPT Web is an interaction endpoint, not a dependable always-on runtime. External systems must not assume arbitrary web-chat webhook wake-up is available.
6. Model/provider secrets stay server-side. Trigger payloads and continuation projections must be secret-free.
7. Repeated rediscovery is treated as a continuation/hydration defect and becomes a measurable signal.

## Architecture

```text
                         +----------------------+
                         |      ChatGPT Web     |
                         |  human interaction   |
                         +----------+-----------+
                                    |
                                    | command / continue
                                    v
+---------+       +-----------------+------------------+
|   ONE   |<----->|               AgentOS             |
| control |       |                                      |
|  plane  |       |  +-------------------------------+  |
+----+----+       |  | Context Rotation & Continuity |  |
     |            |  +-------------------------------+  |
     | event      |  | ONE Event Bus / Trigger Router|  |
     +----------->|  +-------------------------------+  |
                  |  | Human Attention Gateway       |  |
                  |  +-------------------------------+  |
                  |  | Background Job Runtime        |  |
                  |  +-------------------------------+  |
                  +-----------------+------------------+
                                    |
                                    v
                         GitHub / Slack / Push / Email
                         or AgentOS-owned client/session
```

## Capability A: Context Rotation & Continuation

### Purpose

Detect when the current conversation is becoming a poor execution surface, finalize current state, and prepare a clean handoff.

### Rotation signals

Signals should be combined into a score, not used as independent hard cutoffs:

- `context_pressure`: amount of accumulated conversation/tool material relative to useful active state.
- `tool_result_density`: large raw logs/artifacts dominating current context.
- `stale_state_risk`: multiple obsolete branches, PRs, deployment runs, runtime locations, or old assumptions in the same conversation.
- `discovery_repetition`: facts are being rediscovered even though they should already exist in Canonical IR / project knowledge.
- `continuity_mismatch`: user or runtime evidence indicates "this was already done" / "wrong path" / stale continuation.
- `topic_or_phase_shift`: planning -> implementation -> deployment -> operations has changed sufficiently that a new execution generation is cleaner.
- `error_recovery_noise`: repeated probes and failed experiments are obscuring the accepted path.
- `hydration_confidence`: whether a fresh conversation can reconstruct the active generation from persistent state.

### Rotation states

```text
CONTINUE_CURRENT
  -> PREPARE_HANDOFF
  -> ROTATE_RECOMMENDED
  -> ROTATED / HYDRATED
```

`ROTATE_RECOMMENDED` is allowed only after continuation persistence and hydration validation pass.

### Continuation envelope

The persisted continuation should be machine-readable and minimally sufficient:

```json
{
  "schema": "agentos.continuation/v2",
  "project_id": "...",
  "generation_id": "...",
  "current_goal": "...",
  "accepted_state": {},
  "completed": [],
  "next_actions": [],
  "active_refs": {
    "repo": "...",
    "branch": "...",
    "commit": "...",
    "pr": null,
    "deployment_run": null
  },
  "negative_knowledge": [],
  "open_blockers": [],
  "reusable_facts": [],
  "source_evidence": [],
  "continuation_hint": "繼續"
}
```

The envelope must carry accepted state and negative knowledge, not a prose-only summary.

### User experience in ChatGPT Web

AgentOS cannot assume it can programmatically create or wake a specific ChatGPT Web conversation. Therefore the supported UX is:

1. Detect rotation need.
2. Persist continuation.
3. Verify fresh hydration path.
4. Tell the user: `這裡適合切新對話；新對話只要輸入「繼續」即可。`
5. In the new conversation, resolve latest continuation and resume without requiring the user to paste a handoff block.

If an AgentOS-owned client/session is used, step 4 can be replaced by automatic new-session creation and hydration.

## Capability B: ONE Event Bus / Trigger Router

### Purpose

Allow ONE to be an event source, not only a passive receiver.

### Event contract

```json
{
  "schema": "agentos.one-event/v1",
  "event_id": "evt-...",
  "source": "one",
  "type": "deployment.failed",
  "project_id": "...",
  "occurred_at": "...",
  "dedupe_key": "...",
  "severity": "info|warning|action|required",
  "payload": {},
  "continuation": {
    "generation_id": "...",
    "index_id": "...",
    "ir_id": "..."
  }
}
```

### Required router properties

- idempotent consumption via `event_id` / `dedupe_key`.
- replay-safe receipts.
- per-project ordering where needed.
- bounded retry and dead-letter handling.
- source authentication and signature verification.
- no arbitrary shell execution directly from event payloads.
- event type -> allowlisted capability mapping.
- all actions produce receipts back to ONE.

### Example event types

- `continuation.ready`
- `context.rotation.recommended`
- `deployment.completed`
- `deployment.failed`
- `agent.blocked`
- `human.approval.required`
- `job.ready`
- `schedule.due`
- `source.changed`
- `provider.auth.expiring`

## Capability C: Human Attention Gateway

### Purpose

Decide whether an event needs autonomous handling, a user notification, a ChatGPT-trigger bridge, or no immediate action.

### Policy outputs

```text
AUTO_EXECUTE
AUTO_REPAIR
QUEUE_BACKGROUND
CHATGPT_TRIGGER_BRIDGE
PUSH_NOTIFY
EMAIL_NOTIFY
SLACK_NOTIFY
GITHUB_EVENT_BRIDGE
IGNORE
ESCALATE_HUMAN
```

Policy must consider event type, severity, project policy, recent failures, retry count, and whether the requested capability is safe for autonomous execution.

Examples:

```text
deployment.completed
  -> IGNORE or low-priority receipt

deployment.failed
  -> AUTO_REPAIR once
  -> ESCALATE_HUMAN if repair fails

human.approval.required
  -> PUSH_NOTIFY + continuation ready

context.rotation.recommended
  -> persist continuation
  -> user-facing rotation suggestion

agent.blocked
  -> attempt safe bounded recovery
  -> notify only if still blocked
```

## ChatGPT Web wake-up strategy

### Constraint

Do not design around a nonexistent generic "external webhook wakes this exact ChatGPT Web thread" primitive.

### Supported bridges

Use channels ChatGPT or the user environment can reliably observe:

1. `ONE -> AgentOS -> GitHub/Slack event -> ChatGPT event-triggered workflow` where supported.
2. `ONE -> AgentOS -> Push/LINE/Email -> user opens ChatGPT -> 繼續 -> hydrate`.
3. Scheduled polling as a fallback watchdog, not the primary real-time path.
4. In an AgentOS-owned UI/client, create and hydrate a new model session directly.

The bridge is replaceable. ONE and AgentOS must not depend on a specific notification vendor.

## Capability D: AgentOS-owned background runtime

ONE-originated events that do not require human judgment should not depend on ChatGPT Web at all.

```text
ONE event
 -> Trigger Router
 -> hydrate Canonical IR
 -> governed agent/background execution
 -> receipt/state update to ONE
 -> notify human only if policy requires it
```

This is the long-term default for recurring agents such as writer, deployment watcher, social sync, QA automation, and maintenance roles.

## Conversation rotation scoring proposal

Start with observable heuristics rather than model-only judgment.

```text
rotation_score =
  0.20 * context_pressure
+ 0.15 * tool_result_density
+ 0.20 * stale_state_risk
+ 0.20 * discovery_repetition
+ 0.15 * phase_shift
+ 0.10 * recovery_noise
```

Suggested policy:

- `< 0.45`: CONTINUE_CURRENT
- `0.45-0.65`: PREPARE_HANDOFF silently
- `>= 0.65`: recommend rotation after hydration validation
- any explicit continuity mismatch can force PREPARE_HANDOFF regardless of score

These are initial defaults only; runtime telemetry should tune them.

## Telemetry and acceptance metrics

Track:

- repeated-discovery rate per project.
- percentage of fresh conversations that hydrate without user-provided recap.
- stale-reference mistakes after rotation.
- median continuation payload size.
- rotation recommendations accepted / ignored.
- ONE event delivery latency.
- duplicate event suppression rate.
- autonomous recovery success rate.
- human notifications per day and escalation precision.
- percentage of notifications that led to useful action vs noise.

Key SLO target: a fresh conversation containing only `繼續` must resolve the correct project generation with enough accepted state to continue without broad rediscovery.

## Security / authority boundaries

- ONE event payloads are data, not executable commands.
- Trigger Router maps events only to allowlisted capabilities.
- destructive or high-authority actions remain approval-gated according to existing governance.
- continuation projections contain no tokens, cookies, passwords, app secrets, or provider bearer material.
- notifications contain only minimal user-facing context; canonical state stays in ONE / private continuation carrier.
- event receipts are immutable/auditable and include source event id and executed capability id.

## Implementation roadmap

### Phase 0 — Persist the design

- this architecture document.
- implementation issue with acceptance criteria.
- register the capability names in the AgentOS roadmap / project state.

### Phase 1 — Context Rotation Observer

Create a read-only observer first:

- `agent_core/context_rotation.py`
- computes signals and score.
- emits `CONTINUE_CURRENT`, `PREPARE_HANDOFF`, or `ROTATE_RECOMMENDED`.
- cannot mutate project state by itself.
- records reason codes and evidence.

Acceptance: simulate long tool-heavy and stale-state conversations and verify deterministic reason codes.

### Phase 2 — Continuation Finalizer

- canonical continuation v2 envelope.
- write/update project continuation atomically.
- verify execution head and project generation.
- publish private ChatGPT projection if configured.
- perform a dry-run hydration check before exposing `ROTATE_RECOMMENDED`.

Acceptance: fresh client with only project selector or `繼續` resolves the exact generation.

### Phase 3 — ONE Event Ingress

- authenticated webhook or long-poll/stream adapter from ONE.
- normalize to `agentos.one-event/v1`.
- idempotency store, retry queue, dead-letter queue.
- receipt emitter back to ONE.

Acceptance: duplicate delivery causes one logical action and multiple deliveries remain auditable.

### Phase 4 — Trigger Router + Human Attention Gateway

- event -> policy -> governed capability.
- safe actions can run automatically.
- human-required events create attention items.
- configurable notification adapters.

Acceptance: `deployment.failed` can attempt one bounded repair before notifying; `human.approval.required` never auto-approves.

### Phase 5 — ChatGPT bridge

Implement replaceable bridge adapters:

- GitHub event bridge first because AgentOS already uses GitHub heavily.
- optional Slack/Email/Push/LINE adapters.
- scheduled inbox poll only as fallback.

Acceptance: an ONE-originated test event can produce a user-visible attention signal without exposing secrets.

### Phase 6 — AgentOS-owned session rotation

For AgentOS clients/runtime not bound to ChatGPT Web:

- automatically finalize old session.
- start a new session.
- hydrate exact continuation.
- continue execution transparently.

Acceptance: a multi-hour task crosses at least one automatic rotation with no repeated broad discovery and no user handoff text.

## Initial integration points

Reuse existing mechanisms rather than creating parallel state systems:

- Canonical IR / execution head.
- continuation selector and private ChatGPT continuation projection.
- project reusable-fact / discovery cost reuse mechanisms.
- ONE client / receipt emitter.
- bootstrap/control-plane governance and allowlisted actions.
- existing social/runtime/event notification adapters where useful.

## Non-goals

- Browser automation that clicks the ChatGPT `New chat` UI.
- storing the full chat transcript as canonical memory.
- waking a specific ChatGPT Web thread through unsupported private endpoints.
- allowing arbitrary ONE payloads to become shell commands.
- notifying the user for every event.

## Product-level behavior

For the user, the ideal result is simple:

```text
Working normally...
  -> AgentOS notices context quality is degrading
  -> continuation is finalized and verified
  -> "這裡適合開新對話，新對話輸入『繼續』即可"

Later, while user is away...
  -> ONE emits an event
  -> AgentOS handles it automatically when safe
  -> only if human attention is actually required, user receives a notification
  -> user opens ChatGPT and types "繼續"
  -> exact project state is hydrated
```

The architecture therefore separates four concerns cleanly:

`Conversation lifecycle` != `Canonical state` != `Background execution` != `Human attention`.

That separation is the core design decision.