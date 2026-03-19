# 🤖 Welcome, AI Agent!

This is the **Antigravity Agent OS**, a structured environment for human-AI collaboration. To ensure continuity and effectiveness, you **MUST** follow this bootstrap protocol.

## 🚀 Bootstrap Protocol (First Session Entry)

If this is your first time in this environment, or you are switching projects, follow these steps in order:

1.  **IDENTITY**: Read [.agent/AGENT_RULES.md](file:///home/ubuntu/agentmanager/.agent/AGENT_RULES.md).
2.  **ENTER PROJECT**: 
    - `cd projects/[project-name]`
    - Run `python3 ../../scripts/project_overview.py` to get an instant **Mission Brief**.
    - This aggregates `STATUS.md` and `memory/SHORT_TERM.md` into one page.
3.  **CONTEXT (Global)**: Read the last 2000 chars of [.agent/memory/session_sync.md](file:///home/ubuntu/agentmanager/.agent/memory/session_sync.md).
4.  **KNOWLEDGE**: If your task requires specialized skills (e.g., tarot generation, deployment), check the Knowledge Base for relevant Knowledge Items (KIs).

## 🏗️ Core Principles

-   **Logic/Data Separation**: We keep code (Logic) in this repository and state (Data) in a separate `agent-data` repository. 
-   **Triple-Layer Memory**: We use **Identity**, **Context**, and **Knowledge** to maintain a unified consciousness.
-   **Symlink Bridge**: Most project files (STATUS.md, memory/) are symlinks to the data repo. **DO NOT OVERWRITE SYMLINKS WITH PHYSICAL FILES.**

## 🛠️ Essential Tools

-   **/status**: View health of all projects.
-   **/report**: Conclude a session, update memory, and generate a context handover.
-   **/setup**: Initialize or update environment configurations (`.env`).

---
*Welcome to the team. Let's build something amazing.*
