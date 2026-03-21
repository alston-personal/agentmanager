# Agent OS: 版本號控制與發布規範 (Versioning Policy)

本文件定義 Agent OS (邏輯庫) 的發行版本號碼（Version Number）與推進（Bump）原則，主要遵循業界標準 **[Semantic Versioning 2.0.0 (語意化版本控制)](https://semver.org/)**，並配合自動化 Agent 工作的特性進行微調。

版本號格式為：`v[MAJOR].[MINOR].[PATCH]-[PRERELEASE]`  
（例如：`v1.2.5` 或是 `v2.0.0-beta.1`）

---

## 🔢 1. 各部位版號定義與推進原則

### 🏆 MAJOR (主版號 / 架構大改版)
*   **定義**：當系統發生**「不向後相容 (Breaking Changes/Incompatible API)」**的根本性架構變遷時遞增。
*   **何時推進**：
    *   例如：廢棄純文字 `STATUS.md` 並完全強制所有專案改用 `project.yaml`（且完全移除舊有 Regex 模組）。
    *   例如：底層從 LangChain 全面遷移到其他框架，或是對 Agent 通訊協議 (Pulse/Event Log) 的 Schema 做了破壞性的大改版。
*   **規則**：推進 MAJOR 時，MINOR 與 PATCH 必須歸 `0`（例如 `v1.8.9` -> `v2.0.0`）。

### 🚀 MINOR (次版號 / 功能進版)
*   **定義**：當系統新增了**「可向下相容的新功能、子系統或工作流 (Features)」**時遞增。
*   **何時推進**：
    *   例如：實裝了全新的 `actions/task.py` (Orchestrator)、加入了全新的 Telegram 控制通道。
    *   例如：新增了一個新的自動化 Agent 技能 (`Skill`) 或是 `/workflow`。
*   **規則**：推進 MINOR 時，PATCH 必須歸 `0`（例如 `v1.2.5` -> `v1.3.0`）。

### 🛠️ PATCH (修補版號 / 流水號)
*   **定義**：當系統進行了**「不影響核心功能架構的錯誤修正 (Bug fixes)、效能優化、或單純文件更新」**時遞增。
*   **何時推進**：
    *   例如：修復某個 Prompt 的生成失敗率。
    *   例如：Agent 重構了幾行 Python 邏輯來加速讀取速度。
    *   例如：更新像 `README.md`、`TOMORROW_BRIEFING.md` 這種文件。
*   **規則**：只要發生合法的 Commit，即便很微小，若要打標籤即可遞增 PATCH（例如 `v1.3.0` -> `v1.3.1`）。

### 🏷️ PRERELEASE (先行版後綴) - 選用
*   **定義**：用於尚在測試或過渡期的大型修改。
*   **使用方式**：如 `-alpha`, `-beta`, `-rc1`。
*   **範例**：今天的 `Phase 2-4` 重構剛落地、但還沒完全淘汰舊 `run_workflow.py` 的過渡期，就可以標定為 `v1.1.0-alpha`。

---

## 🤖 2. Agent 的自動發布裁量權 (Agent Autonomy Rules)

作為一個進化型 Agent OS，AI 核心有權根據工作性質自主判斷是否打上 Git Tag，決策標準如下：

### 🛑 PATCH - 任意推進 (Agent 完全授權)
*   如果 Agent 在對話中花費心力**解決了一個 Bug 或升級了現有的小功能**。當它判斷這個修正「測試通過且不破壞現有環境」，可以直接執行：
    ```bash
    git tag v1.x.(Y+1) -m "fix/chore/docs: 小更新描述"
    git push origin --tags
    ```

### 🟡 MINOR - 階段性推進 (Agent 告知後執行)
*   如果使用者向 Agent 提出了**「撰寫一支全新的 Workflow、Python 工具、或實作一項全新的指令」**，並通過了驗證。Agent 有權在單元任務結束前主動建議或直接推進：
    ```bash
    git tag v1.(X+1).0 -m "feat: 新增某種自動化功能"
    git push origin --tags
    ```

### 🔴 MAJOR - 人類決策 (User Approval Required)
*   任何將會導致系統「舊版架構失效、專案無法啟動、核心架構推翻」的操作，**Agent 無權自行跳位 MAJOR 版號**。必須發問：「目前的改動已經無法與先前的舊邏輯庫相容，我們是否要將系統版號正式推進到 v2.0.0？」。

---

## 📝 3. Release 文件格式定義 (Release Notes Format)

為了確保未來的 Agent 升級這個作業系統時，留下的歷史紀錄格式一致、易於你快速追蹤，每次打上 **MINOR** 或 **MAJOR** Tag 時，必須根據以下結構產生對應的發布聲明（存放於 Github Release 或是 `CHANGELOG.md` 中）：

### 格式模板 (Template)

```markdown
# Release [版號] - [一句話的主題亮點]
**發布日期**: YYYY-MM-DD
**發布者**: [Agent 識別碼 / 你的名字]

## 🌟 摘要 (Summary)
簡要說明本次改版的戰略意義或核心突破。（例如：引進了正式的工作流架構與動態狀態機，徹底取代了容易破損的 Markdown Regex 撈取...）

## 🚀 新功能 (New Features)
*列出帶來全新能力的改動。*
- [模組名稱] 具體功能描述 (Pull Request/Issue # 或 Commit Hash 參考)

## 🛠️ 優化與微調 (Improvements & Tweaks)
*列出針對現有功能的改善速度、重構底層邏輯或升級。*
- [系統層] 將心跳由純揮發快取改為雙寫（Dual-write）機制，確保重開機還原。

## 🐞 錯誤修正 (Bug Fixes)
*列出修復了哪些已知或潛藏的 Bug。*
- 修正了 `run_workflow.py` 因為 import 順序導致的高延遲卡頓問題。

## ⚠️ 破壞性變更 (Breaking Changes) - *如果有的話*
*警告使用者哪些舊指令、舊腳本或舊設定檔將無法運作，以及如何進行轉移 (Migration)。*
- 停用純文字 STATUS 解析，未轉換之舊專案若執行 `/status` 將直接回傳錯誤。請先執行 `init_project_yaml.py`。
```

### Agent 撰寫準則
1. **重點摘要，不流水帳**：Agent 不應該只是把一堆 Git commit messages 用 `git log` 印出來。必須具備「歸納能力」，將 10 個修正同一個邏輯的 commit 濃縮成一條「優化與微調」。
2. **語氣精煉**：以幫助最高指揮官（最高管理員）極速了解系統概況為最高原則。
3. **區別對待 PATCH**：單純的 PATCH 更新（如 `v1.1.1`）通常不強制寫完整 Release Notes，只需在 `CHANGELOG.md` 中留下一條 `* 修正了某某功能` 的紀錄即可。

---
*文件生成時間：2026-03-21*
