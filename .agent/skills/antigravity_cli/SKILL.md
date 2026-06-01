# 🧩 Antigravity CLI (agy) 開發輔助技能

本技能說明了如何使用 Antigravity CLI (`agy`) 來對本系統的所有專案進行自主程式碼修改、Bug 修復、單元測試執行與專案分析。

## 📌 技能簡介
當使用者要求您修復專案的 Bug、編寫新功能或在特定的 workspace 執行終端命令與驗證時，您不應該只給出說明，而是應該主動呼叫 `run_agy_task` 工具，將任務委派給本地的 `agy` 核心引擎執行。

## 🛠️ 使用場景
1. **程式碼編寫與修復**：修改 `.js`, `.py`, `.ts`, `.html`, `.css` 等檔案。
2. **自動化測試與驗證**：在專案目錄下執行 `npm test`、`pytest` 或 `pnpm build` 等指令來驗證修改是否正確。
3. **專案結構分析**：使用 `agy` 進行跨專案的精準全文檢索（Grep）。

## ⚙️ 呼叫參數說明
呼叫 `run_agy_task` 時，需提供以下參數：
- `project_name` (str): 專案的名稱，例如 `moltbot`、`openclaw`、`leopardcat-tarot`、`zeus-writer`、`agentmanager` 等。
- `task_text` (str): 具體要執行的開發任務說明。請使用明確的指令，例如：「請修改 website/main.js 中的 XX 邏輯，並執行 npm run build 驗證。」
