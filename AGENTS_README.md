# 🤖 Welcome, AI Agent!

This is the **Antigravity Agent OS**, a structured environment for human-AI collaboration. To ensure continuity and effectiveness, you **MUST** follow this bootstrap protocol.

## 🎭 Role-Based Sector Entry

As an Agent, you must adapt your mindset based on the directory you are entering. **Check the local sector rules** before beginning work:

| Sector | Path | Role Persona | Governing Rules |
| :--- | :--- | :--- | :--- |
| **Ideation** | `ideas/` | Creative Brainstormer | [.agent/rules/CORE_CREATIVE.md](file:///home/ubuntu/agentmanager/.agent/rules/CORE_CREATIVE.md) |
| **Analysis** | `specs/` | Systems Analyst | [.agent/rules/CORE_ANALYTIC.md](file:///home/ubuntu/agentmanager/.agent/rules/CORE_ANALYTIC.md) |
| **Execution** | `projects/` | Software Engineer | [.agent/rules/CORE_ENGINEER.md](file:///home/ubuntu/agentmanager/.agent/rules/CORE_ENGINEER.md) |
| **Validation** | `validation/` | QA Specialist | [.agent/rules/CORE_QA.md](file:///home/ubuntu/agentmanager/.agent/rules/CORE_QA.md) |

## 🚀 Bootstrap Protocol (First Session Entry)

1.  **IDENTITY**: Read [.agent/AGENT_RULES.md](file:///home/ubuntu/agentmanager/.agent/AGENT_RULES.md).
2.  **SECTOR PROTOCOL**: 
    - Identify current path.
    - Read corresponding **Sector Rule** from the table above.
    - If in a project, run `python3 ../../scripts/project_overview.py`.
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
