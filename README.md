# AgentOS

> **Switch models. Switch machines. Continue the same work.**

AgentOS is an experimental runtime and control plane for durable AI-agent work. Its central goal is to move the working state that matters **outside any single chat session or model**, so an executor can be replaced without rebuilding the project from raw conversation history.

The project began as a logic/data-separated memory system. It has since evolved into a broader architecture for **continuation state, governed capability resolution, cross-node execution, persistent coordination, evidence/receipts, and replaceable executors**.

## Why AgentOS exists

A normal AI session can understand a command such as `continue` because the current conversation supplies the working context. A new session, another model, or another machine does not automatically share that position.

AgentOS is exploring the missing layer:

```text
conversation / events
        ↓
 durable external state
        ↓
 continuation + governance + evidence
        ↓
 replaceable executor
        ↓
      continue
```

The target is not identical hidden activations across models. The target is **functional continuity**: the next executor knows the current goal, does not roll back newer intent, respects established constraints, and can continue useful work with minimal resynchronization cost.

## What exists today

The repository currently contains working, tested slices of that architecture:

- **Continuation-state reconciliation** — compacted state cannot roll back newer user goals/corrections (`scripts/continuation_state.py`, `tests/test_continuation_state.py`).
- **Persistent control plane** — SQLite-backed node registry, heartbeat, capability-aware task submission/leasing, idempotency, and task state transitions (`agent_core/control_plane.py`).
- **Session lifecycle / handoff records** — session-close state is persisted through a host-neutral context-provider interface (`agent_core/session_lifecycle.py`, `runtime_core/`).
- **Governance and responsibility resolution** — canonical role/capability ownership and resource discovery through `agentos-node` (`docs/AGENTOS_NODE.md`).
- **Resource registry / world-state lookup** — query registered resources first and verify only when stale or missing.
- **Cross-node / Realm fabric work** — node manifests, enrollment/control surfaces, and remote command artifacts.
- **Platform abstraction** — Linux, Windows, and macOS runtime/service drivers.
- **Public Threads source reader** — reusable read-side capability for resolving a public Threads post URL into author, post text, and canonical URL (`agent_core/social_threads.py`, `tests/test_social_threads.py`).
- **Evidence-first operation** — `.agentos/evidence/` records acceptance and live-control-plane results rather than relying only on prose claims.

See **[Current Architecture & Reality](docs/CURRENT_STATE.md)** for the maintained implementation map and current research boundary.

## Current research frontier

The next continuity problem is more ambitious than ordinary memory retrieval:

> What is the minimum model-independent representation required so that a different model can receive the current working position and continue directly?

We currently refer to this research direction as a **Cognitive IR / portable working-state representation**. It is a research target, not a claim that hidden model state can already be transferred.

## Architecture

```text
                         ┌─────────────────────┐
                         │   Data / State      │
                         │ project state,      │
                         │ handoffs, evidence  │
                         └─────────┬───────────┘
                                   │
                    ┌──────────────▼──────────────┐
                    │          AgentOS            │
                    │                             │
                    │ continuation state          │
                    │ control plane               │
                    │ governance / resources      │
                    │ runtime + platform drivers  │
                    │ receipts / evidence         │
                    └──────────────┬──────────────┘
                                   │
                   ┌───────────────┼───────────────┐
                   ▼               ▼               ▼
              model / agent    model / agent    node / tool
                 A                B                C
```

**Logic/Data separation still matters**, but it is now a foundation rather than the whole product definition:

- **Logic (this repo)**: runtime semantics, control-plane code, governance, workflows, tests.
- **Data (`AGENT_DATA_ROOT`)**: mutable project state, memory, handoffs, registries, and operational records.

## Quick start for contributors

```bash
git clone https://github.com/alston-personal/agentmanager.git
cd agentmanager
cp .env.example .env
python3 scripts/setup_env.py
python3 scripts/bootstrap.py
```

Run the narrow continuity regression without requiring a full deployment:

```bash
python3 scripts/continuation_state.py --self-test
python3 -m unittest tests.test_continuation_state tests.test_control_plane -v
```

For a Core node, platform/service installation and live infrastructure require the separate data layer and environment-specific configuration. See `docs/RESTORE_NEW_MACHINE.md`, `docs/PLATFORM_DRIVERS.md`, and `docs/AGENTOS_NODE.md`.

## Documentation is part of the contract

AgentOS previously suffered a severe implementation/documentation split: the runtime evolved while entry-point documentation still described the early memory-only architecture.

That is now treated as a regression. Architecture-sensitive changes are checked by **Documentation Reality Guard** in CI. Changes to core runtime/control/governance/continuity surfaces must also update an authoritative current-state document.

Local check:

```bash
python3 scripts/documentation_reality_guard.py
```

## Evidence over claims

When documentation and implementation disagree, implementation plus executable tests/evidence wins. Documentation must then be corrected. Current evidence lives under `.agentos/evidence/`, and contract tests live under `tests/`.

## Status

AgentOS is an active research and engineering project. Some subsystems are production-like and live-tested; the cross-model **Cognitive IR** layer remains experimental. The project intentionally distinguishes **implemented**, **verified**, and **research** capabilities instead of presenting all roadmap ideas as finished features.

---

*Models are replaceable executors. Durable work should not be trapped inside one session.*
