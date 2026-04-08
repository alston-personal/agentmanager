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

1.  **Environment Setup**:
    ```bash
    cp .env.example .env
    python3 scripts/setup_env.py
    ```
    *Input your GitHub tokens, API keys, and workspace paths when prompted.*

2.  **Bootstrap Data Layer**:
    ```bash
    python3 scripts/bootstrap.py
    ```
    *This creates the necessary folder structure in your data root and establishes symlink bridges.*

3.  **Verify Integrity**:
    ```bash
    /status
    ```

---

## 🛠️ Essential Scripts
- `scripts/reboot_os.sh`: Re-initializes system services and background watchers.
- `scripts/recall_chronicle.py`: Pulls the latest project history from the data layer.
- `scripts/reconcile_workspace.py`: Synchronizes remote project status with the local workspace.

---

## 🛰️ Mission Control (For Agents)
**DO NOT MODIFY LOGIC FILES** unless explicitly performing OS maintenance.
For all daily project work, task management, and memory recall, **ENTER FROM THE DATA LAYER**:

👉 **[Launch Agent-Data View](file:///home/ubuntu/agent-data/README.md)**

---
*「石虎系統：邏輯為骨，數據為魂。」*

