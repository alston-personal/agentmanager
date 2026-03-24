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

## 🌐 Selective Workspace Protocol (跨機器選性同步)

若在非主機環境 (Secondary/Lite Server) 啟動，請遵循以下步驟以最小化資源消耗並維持資料完整性：

1.  **BOOTSTRAP**: 優先執行 `python3 scripts/setup_env.py` (或 `/setup`) 產出本地 `.env` 配置。
2.  **SELECTIVE SYNC**: 勿執行全同步，改用 `python3 scripts/sync_by_sector.py --sector <CATEGORY>` (例如：`Work`) 僅拉取必要專案。
3.  **DATA LINK**: Agent OS 會自動掃描 `agent-data` 的 project.yaml 並建立對應的 Symlink Bridge。
4.  **LOCAL IMPORT**: 若該機器已有運行中的專案，請執行 `python3 scripts/import_project.py` 進行無痛入籍。
5.  **COOPERATIVE REPORT**: 請務必在會話結束後執行 `/report` 將專案進度推回 GitHub，確保主控端與其他分身都能即時看到狀態變更。

---
*Welcome to the team. Let's build something amazing.*
