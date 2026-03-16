# 🛡️ 終極規範：邏輯與資料分離架構 (Logic/Data Separation)

## 📌 核心定義
所有由 AI 指揮中心管理之專案，必須嚴格遵守以下物理分離原則。

### 1. 邏輯層 (Logic Repo) - [專案代碼倉庫]
- **存放內容**：原始碼、組態檔、測試程式。
- **禁止內容**：嚴禁直接儲存實體 `STATUS.md` 或 `memory/` 資料夾。
- **存取規範**：此 Repo 僅負責「怎麼做」。

### 2. 資料層 (Data Repo) - [alston-personal/my-agent-data]
- **存放內容**：`STATUS.md` (進度報告)、`memory/` (AI 長短期記憶)、`logs/` (執行日誌)。
- **本機路徑**：`/home/ubuntu/agent-data/`
- **存放路徑**：`/home/ubuntu/agent-data/projects/[project-name]/...`
- **存取規範**：此 Repo 負責「做了什麼」與「狀態為何」。

## 🔗 連結機制 (The Symlink Bridge)
當 AI 助理進入專案目錄時，必須確保：
- `STATUS.md` -> **指向** `/home/ubuntu/agent-data/projects/[project-name]/STATUS.md`
- `memory/` -> **指向** `/home/ubuntu/agent-data/projects/[project-name]/memory/`

## 🚫 嚴禁行為 (Forbidden Actions)
1. **禁止覆寫軟連結**：嚴禁刪除軟連結並建立同名檔案。
2. **禁止重複提交**：嚴禁將進度數據 (Status) 提交至代碼倉庫 (Code Repo)。
3. **自動檢測**：任何 \`/report\` 指令執行前，必須先驗證 STATUS.md 是否為連結狀態。

*此規範為系統最高準則，任何 Agent 違反此項即視為嚴重失職。*
