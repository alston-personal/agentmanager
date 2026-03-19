# 🚀 Antigravity Agent OS (AgentManager)

**Version: v1.0.0 (The Architect Release)**  
*Date: 2026-03-19*

---

## 🏗️ Architecture: Logic/Data Separation
The **Agent OS** is built on the principle of physical separation between **Behavior (Logic)** and **State (Data)**.
- **Logic Repo (`agentmanager`)**: This repository. Contains source code, rules, workflows, and skills.
- **Data Repo (`agent-data`)**: A private repository linked to `{AGENT_DATA_ROOT}`. Stores memory, project status, and logs.

## 🧠 Triple-Layer Memory System
We've evolved from simple persistence to a tiered consciousness model:
1.  **Identity Layer** 🏛️: Core principles and persona defined in `.agent/AGENT_RULES.md`.
2.  **Context Layer** 🔄: Real-time situational awareness via `memory/SHORT_TERM.md` and global `session_sync.md`.
3.  **Knowledge Layer** 📚: Global facts and specialized skills managed via Knowledge Items (KIs).

## 🛡️ Reliability & Watchdog
A modular watchdog system ensures the system never silently fails. 
- **Watchdog**: Periodically checks Systemd services and External APIs (like n8n).
- **Maintenance**: Automated task aggregation and health snapshots via a systemd timer (every 15 mins).

## 🤖 Universal Onboarding (`AGENTS_README.md`)
Designed for a multi-LLM world. Any AI (Antigravity, Gemini, OpenAI) can instantly enter the context by following the **Bootstrap Protocol** defined in `AGENTS_README.md`.

---

## 🛠️ Quick Start

### 1. Initial Setup
Run the interactive setup tool:
```bash
/setup   # or python3 scripts/setup_env.py
```

### 2. Enter a Project
```bash
cd projects/my-project
python3 ../../scripts/project_overview.py
```

### 3. Report & Handover
Always conclude your session with:
```bash
/report
```
This triggers the `handover.py` script to pass context to the next agent.

---
*Created by Alston & The Antigravity Agent Team.*
