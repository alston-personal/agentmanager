# 🐱 石虎 AgentOS (LeopardCat AgentOS) - 跨代理記憶協議 (LAMP)

## 📖 這是什麼？ (Inter-Agent Memory Layer)
這份手冊是給所有進入本開發環境的 **AI Agent (Antigravity, Codex, Gemini Code Assistant, Cursor, etc.)** 看的。
為了避免「Session 遺失」與「跨工具斷層」，本系統強制要求所有 Agent 遵循 **「物理記憶層」** 機制。

---

## 🚀 Agent 入籍程序 (Onboarding Protocol)
當你（AI Agent）第一次進入任何專案目錄時，**必須**執行以下動作：

1.  **讀取脈搏 (Read Pulse)**：優先開啟 `.agent/pulse/last_brain_dump.md` 與 `STATUS.md`。那裡有上一個 Agent 留下的「靈魂記憶」，而非僅依賴你的 Chat History。
2.  **主動回報 (Heartbeat Update)**：在每一輪對話的核心決策完成後，將 **`Thought`** 與 **`Next Steps`** append 到 `.agent/pulse/live_thoughts.log`。
3.  **結案備份 (Handover Handshake)**：對話結束前，務必執行 `python3 /home/ubuntu/agentmanager/scripts/handover.py` 生成對接手冊。

---

## 📂 記憶目錄結構 (Structure)
每個專案邏輯層 (Logic Repo) 必須包含：
*   `.agent/pulse/`
    *   `last_brain_dump.md`：核心思維與當前難點快照。
    *   `live_thoughts.log`：[重要] 防止 Session 消失的實時紀錄。
    *   `context.json`：結構化的任務變數。
*   `STATUS.md` -> (Link) 指向 Data Layer (真相中心)。

---

## 🚫 禁忌與底線 (The Forbidden Laws)
*   **禁止覆蓋 `STATUS.md` 軟連結**：它是鏈向 `/home/ubuntu/agent-data` 的唯一通道。
*   **禁止自作主張簡化腳本**：嚴禁刪除 `scripts/core_services/` 下的監控腳本。
*   **物理存檔優先**：不要相信對話索引（Index），只相信你寫入磁碟的內容。

---
*「Agent 會離開，但石虎的記憶會留下來。」*
