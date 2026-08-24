# AgentOS Work Graph v1

Status: experimental foundation on `feature/state-kernel-v2`.

## Purpose

The Work Graph answers a question that memory and canonical state do not answer by themselves:

> **Given the current Project HEAD, what should an interchangeable agent continue next?**

The answer must not depend on whichever task happened to be updated most recently, which model is currently active, or whether a new conversation happens to remember the previous one.

## Separation of concerns

```text
ProjectState
= what is operationally true now

Cognitive Memory / Relations
= what the system has learned and how knowledge is connected

Work Graph
= what intended progress remains, in what dependency order, against which base state
```

A WorkItem is not canonical state and does not authorize an external side effect.

## Portable IR

`runtime_core/work_v1.py` defines `agentos.work/v1`.

A WorkItem contains:

```text
work_id
project_id
base_state_id
instruction
capability
depends_on
priority
status
acceptance_criteria
runtime_policy
provider_policy
created_by
metadata
```

The stable `work_id` intentionally excludes lifecycle scheduling fields such as `status` and `priority`.

This is important: a task must keep the same identity while moving

```text
pending -> ready -> running -> done
```

otherwise dependency edges would break every time status changes.

## Deterministic continuation

`InMemoryWorkGraph.select_continue(project_id, head_state_id)` is read-only.

It selects only work whose dependencies are done, then sorts by:

1. work based on the current Project HEAD before stale-base work;
2. higher priority;
3. stable work ID as deterministic tie-breaker.

If only stale-base work remains, it is returned with:

```text
stale_base = true
reason = stale_base_requires_rebase_or_validation
```

The scheduler therefore does not silently pretend work created against an old world state is still safe to execute.

## Dependency governance

- unknown dependency IDs fail closed;
- self-dependency fails closed;
- dependency cycles fail closed;
- terminal `done` / `cancelled` work cannot silently restart;
- status transitions are explicitly constrained;
- Work Graph selection does not mutate ProjectState or execute work.

## Relationship to the phrase “continue”

The target behavior is:

```text
user / agent says: continue
        ↓
read current Project HEAD
        ↓
read Work Graph
        ↓
filter dependency-ready items
        ↓
prefer current-base work
        ↓
deterministic priority selection
        ↓
return selected WorkItem + StateView
        ↓
chosen runtime executes/proposes result
```

So `continue` becomes a project semantic rather than a conversation semantic.

## Current boundary

This foundation does not yet:

- persist Work Graph in the production Control Plane;
- automatically rebase stale WorkItems;
- lease/dispatch the selected work through the production runtime path;
- create WorkItems autonomously from reconciliation or cognitive synthesis;
- authorize external side effects.

Those integrations must preserve the State Kernel and governance boundaries. In particular, SideEffect Ledger remains required before autonomous high-impact external actions.
