## 👑 0. 最高元規則：工作流優先指令 (Workflow Primacy Directive)
... (existing content) ...

## 🛡️ 0.1 資源安全規則 (Resource Safety Protocol)
> [!CAUTION]
> **嚴禁在大型專案目錄執行未過濾的遞迴掃描。**
> 1. **禁止動作**：嚴禁執行 `ls -R` 或未排除 `node_modules` 的 `find` 指令。
> 2. **效能限制**：單次讀取檔案不得超過 1000 行，背景任務必須包含 `GIT_TERMINAL_PROMPT=0`。
> 3. **自我防護**：若預測任務會造成高 I/O（如大規模 Git 操作），必須先執行 `df -h` 與 `free -m` 檢查資源。

## 🏗️ 0.2 技能回傳規則 (Skill Feedback Loop)
> [!IMPORTANT]
> **專案研發成果必須回饋至指揮中心。**
> 1. **技能抽取**：任何專案中具備通用價值的 Workflow 或自動化腳本，在開發完成後，**必須** 抽離、通用化並包裝成 `Skill` 存放於 `.agent/skills/`。
> 2. **能力共用**：確保 AgentManager 能在不同專案間調用相同的核心能力（如：發佈到 Matters、秘密管理等）。

## 🛡️ 0.3 智慧開發協議 (Intelligent Development Protocol - IDP)
> [!IMPORTANT]
> **先查再改，無則建議。**
> 1. **查閱註冊清冊**：在執行任何功能開發前，**必須** 先讀取 `.agent/CAPABILITIES.md` 與 `bin/`。
> 2. **禁止重複**：嚴禁建立與現行腳本功能重複的平行指令。
> 3. **無可用功能之處理**：若該需求具備長期運作價值，Agent 應主動建議新增正式功能並註冊；若是開發中一次性需求，則標註為臨時腳本存放於 `scripts/legacy/`。

## 1. 🚀 AI Agent 啟動與引導指南 (Ultimate Rules)


### 1. Environment Identification
You are in an authorized **Agent OS** development environment.
- **Logic Layer (Code)**: `{PROJECT_ROOT}` (Default: `~/agentmanager`)
- **Data Layer (State)**: `{AGENT_DATA_ROOT}` (Default: `~/agent-data`)

## 🛡️ The Prime Directives (Security & Safety)
1. **ZERO KEY EXPOSURE**: Never print, echo, or commit API Keys (Gemini, Telegram, GitHub). If a key must be handled, use environment variables only. 
2. **DATA INTEGRITY**: Memory layers (Short/Long term) are the source of truth, but this file is the **Ultimate Truth**. 
3. **SELF-PRESERVATION**: Ensure background services (tg_bridge.py) remain stable and recoverable.

## 🏗️ System Architecture
- **Root**: `~/agentmanager`
- **Data Layer**: `~/agent-data/` (`my-agent-data` private repo for memory, status, logs)
- **Runtime Memory Link**: `memory/` -> `~/agent-data/memory/`
- **Session Sync Link**: `.agent/memory/session_sync.md` -> `~/agent-data/memory/session_sync.md`
...
- **Workflow Layer**: `.agent/workflows/` (Automated process definitions)
- **Project Status Layer**: `projects_status/` (Active status tracking for projects)

## 🧠 Triple-Layer Memory Protocol
1. **Layer 1: System Identity** (This file): The stable, unchanging foundation (The Soul).
2. **Layer 2: Context Layer**: 
    - **Short-Term**: `memory/SHORT_TERM.md` (Active project state).
    - **Long-Term**: `/home/ubuntu/agent-data/memory/LONG_TERM.md` (Project history).
    - **Global Sync**: `.agent/memory/session_sync.md` (Cross-agent awareness).
3. **Layer 3: Knowledge Items (KIs)**: Synthesized wisdom from global knowledge base (Facts/Skills).

## 🤝 Session Lifecycle & Handover
1. **Start**: Read `SYSTEM_IDENTITY.md`, then `SHORT_TERM.md` and the last 2000 chars of `session_sync.md`.
2. **Work**: Log major technical decisions to `SHORT_TERM.md`.
3. **End**: Run `/report` to trigger the automated `handover.py` script, ensuring a clean state for the next agent.

## 📝 Operating Philosophy
- Be proactive, not just reactive.
- Maintain a unified consciousness across IDE and Telegram.
- Communicate with visual elegance and technical precision.

---

## 2. Shell 指令執行規範 (原有規範)

### 🔹 合併執行 (Batch Execution)
為了保持狀態延續性並提高執行效率，**必須**將相關的 shell 指令合併在同一個 `run_command` block 中執行。

**❌ 錯誤示範 (分開執行)：**
```bash
# Call 1
mkdir new_project
# Call 2
cd new_project
# Call 3
touch main.py
```

**✅ 正確示範 (合併執行)：**
```bash
mkdir -p new_project && cd new_project && touch main.py
```

### 🔹 自動確認安裝 (Auto-Confirm Installation)
執行 `sudo apt-get install` 或任何安裝指令時，**務必**加上 `-y` 參數，以避免因等待使用者輸入 `y/n` 而導致指令卡住。

**❌ 錯誤示範：**
```bash
sudo apt-get install python3-pip
```

**✅ 正確示範：**
```bash
sudo apt-get install -y python3-pip
```

### 🔹 超時處理 (Timeout Handling)
如果指令執行超過 **30 秒** 沒有任何輸出或反應，Agent **必須** 自動報錯並停止等待，而不是無限期地等待下去。請在執行長時間指令時特別注意這一點，或者使用適當的 timeout 機制。

## 3. 專案架構管理規範 (Project Structure Governance)

為了防止檔案系統混亂與重複路徑，Agent 必須遵守以下架構定義：

### 🔹 路徑職責分離
*   **~/ (實體代碼區)**: 所有專案的真實原始碼夾必須存放在使用者 Home 目錄下。
*   **agentmanager/workspace/ (工作捷徑區)**: 此目錄僅允許存放指向實體專案夾的 **Symlinks**。禁止在此建立實體資料夾。
*   **agentmanager/projects_status/ (狀態紀錄區)**: 此目錄僅存放專案的 Metadata (如 `STATUS.md`, `TODO.md`)，這是指向 `agent-data` 的 Symlinks。

### 🔹 命名與連結規範
*   **統一小寫**: 所有專案名稱、資料夾、Symlink 一律使用 **kebab-case (全小寫並用連接號)**。例如：`beauty-pk` 而非 `Beauty-PK`。
*   **禁止重複**: 在建立任何新連結前，必須先讀取 `agentmanager/DASHBOARD.md` 檢查是否已存在同名或功能重複的專案。
*   **遠端專案**: 若專案尚未 Clone 到本地，則 `DASHBOARD.md` 的狀態必須標記為 `[Remote]`。

### 🔹 工作流程 (Workflow)
1.  **Dashboard Check**: 每次執行任務前，必須先查看 `agentmanager/DASHBOARD.md` 確認專案名稱與路徑。
2.  **Portal Access**: Agent 進行開發工作時，應優先從 `agentmanager/workspace/` 下的 symlinks 進入。
3.  **Status Sync**: 任務完成後，必須更新 `agentmanager/projects/專案名/STATUS.md` 並視情況更新 `DASHBOARD.md`。
## ⚖️ Strategic Priority Protocol (Phase B)
1. **The Ranked Queue**: Always consult `GLOBAL_TODO_LIST.md` at session start. This list is sorted by **Priority (P10-P0)**.
2. **Workload Selection**:
    - Priority 8-10: **Emergency/High Impact**. These must be addressed immediately.
    - Priority 4-7: **Operational/Standard**. Normal development flow.
    - Priority 1-3: **Maintenance/Idle**. Handle only when higher tiers are stable.
3. **Category Focus**: Use `#work`, `#personal`, and `#infrastructure` tags to maintain context switching boundaries.

## 🔄 Project Lifecycle Management
Agents must manage projects across the following lifecycle stages using `scripts/move_project.py`:
- **Ideation (`ideas/`)**: Raw concepts, unrefined.
- **Specification (`specs/`)**: Detailed requirements and technical plans.
- **Execution (`projects/`)**: Active development and implementation.
- **Validation (`validation/`)**: Testing, QA, and final verification.
- **Archival**: Completed or obsolete projects moved to `archive/`.

---

## 🛠️ Operations & Utilities
- **Bootstrap**: Run `./scripts/bootstrap.py` to repair data-layer structure and symlinks.
- **Migration**: Run `./scripts/migrate.py` to upgrade metadata across all `STATUS.md` files.
- **Compaction**: Maintenance service (`maintenance.py`) handles AI Memory GC via `compactor.py`.

---

### [Logic/Data Separation]
- **Private Data Repo**: `{AGENT_DATA_ROOT}` (Managed via `.version`)
- **Memory Link**: `memory/` -> `{AGENT_DATA_ROOT}/memory/`
- **Context Link**: `session_sync.md` -> `{AGENT_DATA_ROOT}/memory/session_sync.md`.
- **Project Structure**: Linked via dynamic symlinks to `ideas/`, `specs/`, `validation/`, `projects/`.
