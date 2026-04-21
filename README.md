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

4.  **Install core user services** (Core machines only):
    ```bash
    bash scripts/install_systemd_user.sh
    ```
    *Set `AGENT_MODE=CORE` in `.env` before this step if this machine should run Telegram, Cat-Ink memory sync, and watchdog services.*

5.  **Verify Integrity**:
    ```bash
    /bin/bash scripts/health_check.sh
    python3 scripts/run_workflow.py status
    ```

---

## 🛠️ Essential Scripts
- `scripts/reboot_os.sh`: Re-initializes system services and background watchers.
- `scripts/install_systemd_user.sh`: Installs portable user-level systemd units for a cloned machine.
- `scripts/recall_chronicle.py`: Pulls the latest project history from the data layer.
- `scripts/reconcile_workspace.py`: Synchronizes remote project status with the local workspace.

---

## 🛰️ Mission Control (For Agents)
**DO NOT MODIFY LOGIC FILES** unless explicitly performing OS maintenance.
For all daily project work, task management, and memory recall, **ENTER FROM THE DATA LAYER**:

👉 **[Launch Agent-Data View](file:///home/ubuntu/agent-data/README.md)**

---
*「石虎系統：邏輯為骨，數據為魂。」*
