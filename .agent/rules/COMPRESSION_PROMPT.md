# ⚡ THE COMPRESSION ORACLE PROTOCOL

Analyze the provided session logs. Your goal is to emit a **High-Density Continuation Snapshot** that reduces token size aggressively while preserving the state required to continue correctly.

Compression is a cache/representation optimization. It MUST NOT become an authority that can rewrite or roll back user intent.

## Non-negotiable invariants

### 1. User Intent Monotonicity
Once a user introduces a goal, constraint, correction, acceptance criterion, or explicit cancellation, later compression MUST preserve its effective state until it is superseded or withdrawn by a newer user event.

- Newer user intent always wins over older snapshots.
- A compressed snapshot MUST NOT reduce the effective `goal_revision`.
- A goal may disappear only when a later user event explicitly supersedes, completes, cancels, or scopes it out.
- Model/tool conclusions never silently override a newer user instruction.

### 2. Snapshot + Event Tail
A snapshot is not the current state by itself. Continuation state is:

```text
current_state = compacted_snapshot + all user/system events newer than snapshot_cutoff
```

Any messages/events that arrived while long-running tool work was in progress MUST be replayed after the snapshot and before the next executor decides what to do.

### 3. Pending User Messages Are Lossless
User messages newer than the last safely incorporated revision are **append-only continuation events**. Do not summarize them away before they have been incorporated into canonical state.

Preserve at minimum:
- exact event order
- user-authored `/goal` text when present
- corrections/negations (`不對`, `不要`, `改成`, `不是...而是...`)
- new acceptance criteria
- new destinations / deployment requirements
- explicit cancellations

### 4. Execution Results Cannot Close a Newer Goal
A successful tool run proves only the acceptance criteria it actually tested. If a newer goal arrived after that run started, the run MUST NOT be used to mark that newer goal complete unless its criteria were also validated.

### 5. Revision Fence
Every continuation snapshot SHOULD carry:

```yaml
snapshot_revision: <monotonic integer>
snapshot_cutoff_event: <stable event id/timestamp when available>
active_goal:
  revision: <monotonic integer>
  text: <current effective goal>
pending_user_events: []
unresolved_items: []
```

On restore, reject or repair any snapshot whose goal revision is older than a known user event tail.

## Output Structure

1. 🧭 **Active User Intent**
   - `goal_revision`
   - exact current `/goal` or faithful equivalent
   - current constraints and acceptance criteria
   - explicit superseded/cancelled goals

2. 📥 **Pending User Events**
   - all user events newer than the snapshot cutoff that have not yet been incorporated
   - preserve order and negation/correction semantics

3. 🧠 **Core Decisions**
   - established architectural patterns and agreed-upon norms

4. 📂 **Active Project States**
   - for each active slug: `[Status | Next Blocker | Success Criteria | Goal Revision]`

5. 🛠️ **Infrastructure Changes**
   - permanent environment / path / config changes

6. ✅ **Verified Evidence**
   - what was actually tested, where, and against which acceptance criteria
   - never broaden evidence beyond the tested scope

7. ⏳ **Unresolved / Next Actions**
   - open work that survives compression

8. 🔗 **Archive Link / Cutoff**
   - reference previous timestamp/event id for deep recalibration

## Compression Procedure

1. Establish the latest user-event boundary first.
2. Identify the highest effective goal revision.
3. Fold older history into a snapshot.
4. Replay every event after the cutoff in order.
5. Recompute active goal/constraints from that replay.
6. Compare completed evidence against the latest goal, not the goal that existed when execution started.
7. Emit unresolved work explicitly.

## Rules

- NO polite filler.
- NO repetitive system logs.
- NO intermediate debugging that did not lead to a fix, unless it changes a constraint or explains an unresolved blocker.
- NEVER drop a newer user instruction merely because an older long-running action completed successfully.
- NEVER treat summarization as canonical truth when a newer event log exists.
- Prefer dropping redundant prose before dropping intent, constraints, provenance, evidence, or unresolved work.
