# ⚙️ LeopardCat AgentOS: Logic Layer
> **The Brain-Stem of your AI Operating System.**

This repository contains the core logic, automation scripts, and workflows that power **LeopardCat AgentOS**.

---

## 🏗️ The Architecture (Logic vs. Data)
To ensure permanent memory and easy migration, AgentOS uses a **Logic/Data Separation** model:
*   **Logic (This Repo)**: Stateless scripts, workflows, and binaries.
*   **Data ([agent-data](file:///home/ubuntu/agent-data))**: Your unique history, project statuses, and long-term memory.

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

---

## 🛰️ Mission Control (For Agents)
**DO NOT MODIFY LOGIC FILES** unless explicitly performing OS maintenance.
For all daily project work, task management, and memory recall, **ENTER FROM THE DATA LAYER**:

👉 **[Launch Agent-Data View](file:///home/ubuntu/agent-data/README.md)**

---
*「石虎系統：邏輯為骨，數據為魂。」*
