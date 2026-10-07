# AgentOS Context Ownership and Continuation Protocol

Status: initial normative contract

## Purpose

AgentOS must not interpret an implicit `continue` request by loading the globally most recent work. In a multi-node, multi-executor system that behavior causes context leakage and can resume the wrong task.

The continuation contract is local-first and work-centered.

## Identity scopes

AgentOS recognizes these independent identities:

- `agentos://global` — system policy, global goals, registries, cross-node summaries.
- `node://<node-id>` — host capabilities, health, inventory and assigned work summary.
- `runner://<node-id>/<runner-id>` — queue, lease and dispatch state only.
- `executor://<node-id>/<executor-id>` — runtime execution state and physical checkpoint.
- `participant://<participant-id>` — model/agent-specific context.
- `work://<work-id>` — durable logical goal, progress and acceptance state.
- `session://<session-id>` — disposable interaction state.

## Primary invariant

> Session can die, Participant can change, Executor can change, and Node can change, but Work must survive.

Work IR is therefore the durable center of continuation. Other scopes reference a Work ID rather than duplicating the full Work IR.

## Ownership

| Scope | Owns | Must not own |
| --- | --- | --- |
| Global | policy, topology, global goal summaries, registry | executor transient runtime |
| Node | host health, capabilities, executor inventory, node assignments | complete global IR |
| Runner | queue, lease, dispatch metadata | business/work IR |
| Executor | runtime state, local resources, physical checkpoint | canonical goal/acceptance |
| Participant | participant-specific context and bindings | node-global state |
| Work | goal, plan, logical progress, acceptance, durable continuation cursor | host-specific PID/session details |
| Session | transient conversation context | sole copy of durable progress |

## Continue resolution

An implicit `continue` must resolve a Work binding in this order:

1. Explicit Work ID.
2. Existing session binding.
3. Matching participant + executor + node binding.
4. Matching executor + node binding.
5. Work explicitly assigned to the current node.
6. Compatible unbound/global assignment.
7. Otherwise return `NO_CONTINUATION`.

The resolver must never select work merely because it is globally newest.

A global assignment already targeted to another node is not a fallback candidate.

## Logical vs physical checkpoint

Work IR owns logical progress, for example:

- completed step
- next step
- acceptance state
- verified evidence
- blocker

Executor IR owns physical state, for example:

- browser profile
- process id
- working directory
- local port
- ephemeral session identifiers

Same-executor recovery may use both logical and physical restore. Cross-executor or cross-node recovery must assume physical state is non-portable unless a capability explicitly declares otherwise.

## Receipt projection

Receipts should converge on these identity fields:

```yaml
work_id:
node_id:
runner_id:
executor_id:
participant_id:
session_id:
action:
ok:
logical_state_before:
logical_state_after:
executor_checkpoint_ref:
verified:
observed_at:
```

Not every field is mandatory for legacy v0.1 receipts. New execution paths should populate all identities known at dispatch time.

## Required acceptance cases

1. Node-local continuity — a new conversation on Node A resumes Node A's work.
2. Node isolation — Node A must not resume Node B's active work.
3. Participant isolation — Gemini and Codex on one node do not steal each other's work.
4. Executor isolation — GUI and CLI executors do not share transient state.
5. Fresh node fallback — a node without local work only resumes work explicitly assigned to it, then compatible global work.
6. Session loss — a new session can resume durable Work state.
7. Executor restart — logical continuation survives executor process loss.
8. Cross-executor handoff — physical state is rebuilt while logical progress survives.
9. Cross-node handoff — target node receives Work IR plus portable checkpoint/evidence only.
10. Complete runtime loss — durable Work progress remains recoverable from the control plane.

## Continuity benchmark

Suggested levels:

- L0: same conversation continuity
- L1: new session / same participant continuity
- L2: executor restart continuity
- L3: node restart continuity
- L4: cross-node continuity
- L5: cross-executor / cross-model continuity
- L6: goal continuity after complete runtime loss

These levels can be measured by AgentOS Growth Proof using success rate, human intervention rate, recovery time, replay count and acceptance pass rate.
