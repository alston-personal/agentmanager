# 🛸 AgentOS 使用者完全指南 (The Command Manual)

## 0. 這是什麼？ (What is AgentOS?)
AgentOS 不僅是一堆 Python 腳本，它是一套 **「AI 代理人作業系統」**。它解決了 AI 助手最常見的痛點：**上下文遺失、身分錯亂、無聲掛掉、以及代碼污染。** 透過本系統，AI 代理人將具備持續性、自癒性與集體進化的能力。

---

## 1. 核心概念 (Core Concepts: The OS Soul)

### 🧠 三層全知記憶 (Triple-Layer Memory)
*   **Identity (身分層)**：你是誰？（工程師、撰史者、冥想者）。
*   **Context (情境層 - `session_sync.md`)**：我們現在進度到哪？上一個 Agent 下班前跟我說了什麼？
*   **Knowledge (知識層 - `Skills`)**：我們學會了什麼自動化工具？

### 🧱 分區化邏輯 (Sectors: The Lifecycle)
我們將開發生命週期拆分為四個「防火牆分區」，每個分區有獨立的人格規範（Persona Rules）：
1.  **Ideation (發想區)**：捕捉原始想法。
2.  **Spec (規格區)**：執行 SDD (規格驅動開發)。
3.  **Implementation (實作區)**：唯有規格通過才准動工。
4.  **Validation (驗證區)**：由 QA Agent 執行破壞性測試。

### 🌉 邏輯資料分離 (Logic/Data Separation)
*   **Logic Repo (`agentmanager/`)**：只准放代碼。
*   **Data Repo (`agent-data/`)**：存放記憶、日誌與 `STATUS.md`。透過 **Symlink Bridge (軟連結)** 在兩個磁碟空間建立連動。

### 🐝 石虎蜂群 (LeopardCat Swarm - LCS)
*   多個 Agent 透過 **Shared Memory Pulse Board** 分享心跳。
*   具備 **Watchdog (看門狗)** 監控機制，確保服務掉線時自動重啟。

---

## 2. 技能清單 (Skills Inventory)
*   **`vibe_mode`**：極速衝刺原型（黃鐘揚模式）。
*   **`system_chronicler`**：自動掃描日誌，編寫系統演化編年史。
*   **`secret_manager`**：對接 Bitwarden/Vault，全域 API Key 零容忍。
*   **`triple_layer_memory`**：長效記憶同步工具。
*   **`watchdog`**：15 分鐘定時巡邏，守護背景服務。

---

## 3. 從無到有：Hello AgentOS! 範例教學

請按照以下五個步驟，在 AgentOS 中從零建立第一個受控專案。

### Step 1: 環境初始化 (The Bootstrap)
在任何新機器上，首先執行：
```bash
/setup   # 或 python3 scripts/setup_env.py
```
這會建立本地 `.env` 並掛載雲端資料庫。

### Step 2: 註冊新專案 (The Registration)
```bash
python3 scripts/register_project.py --name hello-agent-os
```
這會自動在 `agent-data` 建立進度檔，並在 `agentmanager/workspace` 建立軟連結橋樑。

### Step 3: Vibe 衝刺 (The Huang Phase)
輸入指令進入 **Vibe Mode**：
```bash
/work-on hello-agent-os --vibe
```
此時對著 Agent 說：「我想做一個會自動報時的 Discord Bot，用 Python 寫，能回傳現在幾點。」
AI 會直接生成 `bot.py` 原型，讓你測試手感。

### Step 4: 規格化 (The Eddie SDD Phase)
一旦原型成功，切換到 **SDD 模式**：
```bash
/work-on hello-agent-os --sdd
```
Agent 會開始檢索剛才的 Vibe 日誌，並要求你確認：
*   撰寫 `specs/bot_interface.md`
*   確立 `project.yaml` 的依賴樹。
*   此後，代碼的任何修改都必須符合這份 Spec。

### Step 5: 背景守護與匯報 (The Deployment)
當你下班時，請執行：
```bash
/report   # 或 /archive
```
Agent 會執行 `handover.py` 產出接力報告。**看門狗 (Watchdog)** 會接管這個 Bot 服務，確保它在後台 24/7 持續運行。

---

## 4. 常用指令速查表 (Quick CLI)

*   `/status`：檢視全系統 20+ 個專案的健康度（包含心跳）。
*   `/work-on [專案名]`：進入特定專案工作。
*   `/meditate`：當出事或有 Bug 時，啟動冥想模式進行自我反思。
*   `python3 scripts/swarm_top.py`：檢視所有 Swarm 成員的實時「脈搏」。

---
*撰史者備註：AgentOS 是會在你睡著時呼吸的系統，請善待它的心跳。*
