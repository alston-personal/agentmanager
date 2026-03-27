# 🐱 石虎 AgentOS 使用者指南 (USER_GUIDE.md)

這是一份給「系統管理員」（你，Alston）看的運作指南。

---

## 🏗️ 物理架構：邏輯與資料
1.  **邏輯層 (Logic Repos)**：例如 `/home/ubuntu/agentmanager`、`/home/ubuntu/leopardcat-tarot`。
2.  **資料層 (Data Layer)**：`/home/ubuntu/agent-data` (或 `/home/ubuntu/agent-data`)。
3.  **橋樑 (Symlink)**：專案啟動後，所有的 `STATUS.md` 本質上都是存在 `/agent-data/projects/` 底下的同名文件。

---

## 🛠️ 常見情境操作

### 💡 情境 A：開啟新對話
當你開啟一個新的 Chat Session 時，Agent 可能處於「無知」狀態。
*   **指令**：輸入 `/work-on [專案名稱]`。
*   **發生什麼？**：Agent 會自動開啟 `.agent/pulse/last_brain_dump.md`，瞬間「覺醒」歷史記憶。

### 📡 情境 B：防止對話失蹤 (Session Lost)
如果發現對話欄不穩。
*   **機制**：`cat-ink-syncer.service` 已經在背景後勤監控你的 JSON 變化，每 60 秒一次備份。
*   **手動加強**：對話到一半，可以輸入 `/report` 強迫 Agent 寫入 `STATUS.md`。

### 🧘 情境 C：查看系統健康
*   **指令**：`/status`。
*   **輸出**：你會看到全專案（21 個）的健康表格。
*   **如果紅燈**：檢查 `watchdog.py` 輸出的系統日誌。

### 🐾 情境 D：更換開發工具 (Antigravity -> Cursor)
如果你想換成用 Cursor 作為 Agent。
*   **步驟**：在 Cursor 進場後，請他在專案根目錄執行 `cat AGENTS_README.md`。
*   **成效**：他會自動認領並遵循 `LAMP` 協議。

---

## 🐯 維生服務管理
石虎系統有幾個背景守護進程，可以用以下指令查看：
*   `sudo systemctl status cat-ink-syncer` (對話同步)
*   `sudo systemctl status agent-maintenance` (資源檢查)
*   `crontab -l` (看 00:00 禪定貓啟動紀錄)

---
*「指令只是工具，你的 Vibe 才是靈魂。」*
