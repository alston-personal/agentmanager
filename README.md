# ⚙️ LeopardCat AgentOS: Logic Layer
> **The Brain-Stem of your AI Operating System.**

This repository contains the core logic, automation scripts, and workflows that power **LeopardCat AgentOS**.

---

## 🏗️ The Architecture (Logic vs. Data)
To ensure permanent memory and easy migration, AgentOS uses a **Logic/Data Separation** model:
*   **Logic (This Repo)**: Stateless scripts, workflows, and binaries.
*   **Data ([agent-data](file:///home/ubuntu/agent-data))**: Your unique history, project statuses, and long-term memory.

---

## 🌐 Distributed AgentOS
AgentOS is evolving beyond a full Runtime installed on every device. The distributed architecture uses **Canonical IR** as the shared continuation contract and treats IDE clients, local devices, web agents, GitHub Actions, provider APIs, and future cloud workers as capability-specific participants around one durable Control Plane.

- `runtime_core/canonical_ir.py` — portable Canonical IR + lineage/digest/hop tracking
- `runtime_core/remote_runtime.py` — capability-gated Remote Runtime contract
- `agent_core/distributed_control_plane.py` — task lease/result/continuation semantics, including exact push-task lease
- `agent_core/project_state.py` — project-scoped current Canonical IR read model for cross-IDE continuation
- `agent_core/runtime_dispatcher.py` + `agent_core/push_dispatch.py` — local-first routing, durable push targets, retry/dedupe, GitHub/webhook wake-up
- `agent_core/dispatching_gateway.py` — closes submit/complete → dispatch loop
- `agent_core/continuity_mirror.py` — best-effort private Data Layer mirror for connector-only agents
- `agentos_node/control_plane_client.py` + `agentos_node/remote_worker.py` — lightweight runtime without full AgentOS Host
- `agentos_node/ide_adapter.py` + `agentos_node/ide_cli.py` — portable `agentos` CLI for VS Code/Cursor/Antigravity/JetBrains/SSH/CI
- `agentos_node/web_agent_adapter.py` — trusted Web Agent request/result contract
- `agentos_node/provider_bridge.py` — capability-routed Provider Registry for OpenAI, Gemini, OpenAI-compatible proxies, and authorized relays
- `agentos_node/provider_bridge_server.py` — asynchronous authenticated wake endpoint for provider runtimes
- `.github/workflows/distributed-agentos-worker.yml` — GitHub Actions Runtime Worker with exact task binding
- `.agentos/project.json` — stable, non-secret project identity shared across clones/IDEs
- `docs/DISTRIBUTED_AGENTOS_RUNTIME.md` — overall architecture and migration path
- `docs/DISTRIBUTED_CONTROL_PLANE.md` — Control Plane protocol
- `docs/IDE_ADAPTER.md` — cross-IDE install/continue/delegate workflow
- `docs/CONTINUITY_MIRROR.md` — private GitHub fallback mailbox for connector-only agents
- `docs/WEB_AGENT_ADAPTER.md` — browser/web-agent boundary
- `docs/RUNTIME_DISPATCHER.md` — active routing and wake-up policy
- `docs/PROVIDER_BRIDGE.md` — provider routing, deployment, security, and browser-relay boundary

The design rule is: **Canonical IR is the continuity boundary; runtime location and IDE session are implementation details.** GitHub Actions, model providers, and IDE chats are not the durable AgentOS brain.

The active continuation path is now:

```text
IDE / Agent / Runtime A
  → Canonical IR or verified Runtime Result
  → trusted Continuation IR
  → Control Plane project state
  → Runtime Dispatcher
  → local exact/pull lease OR active GitHub/Provider Bridge wake-up
  → capability/provider routing
  → Agent/Runtime B
```

For agents that cannot directly reach the Control Plane but can access the private Data Layer, the Core can mirror the latest project checkpoint to `projects/<project-id>/continuity/latest.json`. The Control Plane remains authoritative; the mirror is a connector-readable fallback only.

Push wake-ups carry an exact `task_id`; the runtime must atomically lease that same task before execution. Push target metadata is durable in the Control Plane database while transport/provider secrets remain outside the registry. Pending tasks are swept after Core restart and failed/stale wake-ups use bounded retry recovery.

### Cross-IDE client

A development machine does **not** need the full AgentOS Host. Install the portable package and point it at the shared Control Plane:

```bash
python -m pip install -e .
export AGENTOS_CONTROL_PLANE_URL=https://agentos.example.com
export AGENTOS_CONTROL_PLANE_TOKEN=replace_with_authorized_client_token

agentos status
agentos continue
```

For a newly added project, run `agentos init <stable-project-id>` once and commit `.agentos/project.json`. See `docs/IDE_ADAPTER.md`.

---

## 🚀 Quick Start (Installation)

If you are setting up this system on a new machine:

1.  **Clone both layers**:
    ```bash
    cd ~
    git clone https://github.com/alston-personal/agentmanager.git
    git clone https://github.com/alston-personal/my-agent-data.git agent-data
    cd agentmanager
    ```

2.  **Environment Setup**:
    ```bash
    cp .env.example .env
    python3 scripts/setup_env.py
    ```
    *Input your GitHub tokens, API keys, and workspace paths when prompted.*

3.  **Bootstrap Data Layer**:
    ```bash
    python3 scripts/bootstrap.py
    ```
    *This creates the necessary folder structure in your data root and establishes symlink bridges.*

4.  **Install user services** (mandatory on Core, optional on Client):
    ```bash
    python3 scripts/install_services.py
    ```
    *This now routes through the platform driver layer. Linux can still use systemd, while Windows and macOS fall back to local runtime/service registries. Set `AGENT_MODE=CORE` in `.env` before this step if this machine should run Telegram, Cat-Ink memory sync, and watchdog services.*

5.  **Verify Integrity**:
    ```bash
    /bin/bash scripts/health_check.sh
    python3 scripts/run_workflow.py status
    ```

---

## 🛠️ Essential Scripts
- `scripts/reboot_os.sh`: Re-initializes system services and background watchers.
- `scripts/install_systemd_user.sh`: Installs portable user-level systemd units for a cloned machine.
- `scripts/install_services.py`: Platform-aware service installer entrypoint.
- `scripts/platform_runtime.py`: Platform-aware runtime selector and diagnostics.
- `scripts/distributed_gateway.py`: Distributed Control Plane + active Runtime Dispatcher gateway.
- `scripts/distributed_remote_worker.py`: Single-shot lightweight remote Runtime Worker.
- `scripts/provider_bridge.py`: Provider Bridge runtime for OpenAI/Gemini/proxy/browser-relay providers.
- `scripts/recall_chronicle.py`: Pulls the latest project history from the data layer.
- `scripts/reconcile_workspace.py`: Synchronizes remote project status with the local workspace.

---

## 🧩 Platform Driver Architecture
AgentOS now separates:

- **Core logic**: `agent_core/session_lifecycle.py`, workflows, status parsing, and session close protocol
- **Platform drivers**: `agent_core/platform/{base,linux,windows,macos}.py`
- **Runtime entrypoints**: `scripts/pulse.py`, `scripts/install_services.py`, `scripts/platform_runtime.py`

The drivers expose a single capability surface for:

- runtime / volatile / persistent state paths
- pulse and event writes
- service install / start / stop / restart
- recurring job registration
- transcript syncing
- project link repair

Linux can still lean on `systemd` and `/dev/shm`; Windows and macOS use local runtime directories plus subprocess-backed service state.

See [docs/PLATFORM_DRIVERS.md](docs/PLATFORM_DRIVERS.md) for the compact architecture note.

## 🧠 Memory Routing
Memory writes now resolve through `agent_core/memory_router.py` before anything touches disk.

- explicit context env wins first: `AGENT_CONTEXT_PROJECT_ROOT`, `CLAUDE_PROJECT_DIR`, `AGENT_ACTIVE_PROJECT_ROOT`
- otherwise the router inspects the current workspace for `STATUS.md` and `memory/` bridges
- if nothing matches, it falls back to the logic repo defaults

This keeps `SHORT_TERM.md`, `LONG_TERM.md`, transcripts, and session records pointed at the intended project instead of whichever workspace happened to be opened first.

---

## 🛰️ Mission Control (For Agents)
**DO NOT MODIFY LOGIC FILES** unless explicitly performing OS maintenance.
For all daily project work, task management, and memory recall, **ENTER FROM THE DATA LAYER**:

👉 **[Launch Agent-Data View](file:///home/ubuntu/agent-data/README.md)**

---
*「石虎系統：邏輯為骨，數據為魂。」*
