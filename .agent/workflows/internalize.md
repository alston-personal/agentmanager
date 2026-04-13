---
description: 將最近的專案進展、錯誤修復或技術發現內化為結構化的 LLM Wiki (Knowledge Item)
---
# 🧠 知識內化工作流 (Internalize Knowledge)

此工作流根據 Andrej Karpathy 的 "Stop RAG, Start Wiki" 理論，將碎片化的資訊轉化為高密度的、可互聯的結構化知識。

### 1. 資訊採集 (Ingest)
- 讀取 `memory/SHORT_TERM.md` 與最近的 `logs/`。
- 讀取當前對話中的關鍵技術決策或錯誤修復紀錄。

### 2. 知識蒸餾 (Distill)
- 提取「實體」(Entities)、「技術參數」、「架構模式」與「踩雷紀錄」。
- **Leeloo 壓縮**：去除冗贅對話，只保留高機率在未來被重複使用的「純粹事實」。

### 3. 知識定位與對比 (Map & Conflict Check)
- 檢查 `~/.gemini/antigravity/knowledge/` 是否已有相關主題。
- 確保新知識不會與舊知識產生未說明的衝突。

### 4. 寫入 Wiki (Write)
- **新知識**：建立新目錄並包含 `metadata.json` 與 `artifacts/CONTENT.md`。
- **更新**：在現有文件中增補內容，並標註「$(date +%Y-%m-%d) 更新」。
- **語法規範**：使用 `[[TopicName]]` 進行雙向連結。

### 5. 建立 MOC (Map of Content)
- 確保所有新知識至少連結回一個核心地圖（如 `[[AgentOS_Arch_MOC]]`）。

---
*執行指令：`/internalize`*
