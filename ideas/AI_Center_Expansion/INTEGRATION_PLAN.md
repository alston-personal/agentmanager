# 📥 AI Center 系統整合分析報告 (Integration Plan)

## 1. 積木化建模 (N8n Sub-workflow Definitions)

我們將所有發想拆解為以下可重複使用的 **Atomic Workflows**：

### A. [Media-Ingestor] 多媒體擷取節點
- **Input (JSON)**: `{"source_url": "string", "type": "ivod|youtube|sd_path"}`
- **Output (JSON)**: `{"raw_content_path": "string", "metadata": {}}`

### B. [VLM-Analyzer] 視覺解讀與標籤節點
- **Input (JSON)**: `{"image_path": "string", "context": "commercial|gaming|spatial"}`
- **Output (JSON)**: `{"tags": [], "description": "string", "actions_suggested": []}`

### C. [Strategy-Iterator] 策略自我演化節點
- **Input (JSON)**: `{"performance_mdd": float, "current_params": {}, "history_log": "string"}`
- **Output (JSON)**: `{"new_params": {}, "prompt_update": "string"}`

---

## 2. 通用核心模組 (Shared Core Modules)

為了降低系統開發成本，我們將提取以下「通用核心節點」：

1.  **`Core-Vision-Service`**: 統一對接 GPT-4o-vision 或 Gemini 1.5 Pro，處理圖庫標籤、電玩畫面辨識、NASA 數據分析。
2.  **`Graph-Intelligence-Bridge`**: 負責將關係資料（族譜系統、利益衝突、立委金主）轉化為 Mermaid 或 D3.js 視覺化 JSON。
3.  **`Vector-Memory-Indexer`**: 處理公民監督站的 Whisper 逐字稿、量化交易的歷史數據索引。

---

## 3. 硬體 / 外部接口協議 (Interface Protocols)

| 設備/系統 | 通訊協議 | N8n 接入方式 |
| :--- | :--- | :--- |
| **PS5 (HID Control)** | Arduino Serial over Websocket | N8n -> HTTP Request -> Local Node.js Bridge -> Arduino |
| **NFC (Proximity)** | Android/iOS App Webhook | N8n -> Push Notification (Firebase) -> APP Trigger NFC |
| **Unity (Visualization)** | REST API (POST) | N8n -> HTTP Request (JSON) -> Unity WebGL Context |

---

## 4. 第一階段開發 Roadmap 建議 (Top 3 Priorities)

考慮到資源與現有環境工具，建議導進以下三個「實體積木」：

### 🏁 優先級 1：圖庫自動化營收系統 (Stock Autopilot)
- **原因**：流程最閉環，且有直接變現（Passive Income）潛力。
- **缺失節點**：Shutterstock API 封裝 (或是模擬上傳的 Selenium 腳本)。

### 🏁 優先級 2：獨立公民監督站 (Citizen Watch)
- **原因**：利用現有的 Whisper 與 AI 索引能力，不需要額外硬體，純數據處理。
- **缺失節點**：IVOD 自動下載器模組。

### 🏁 優先級 3：量化交易策略迭代器 (Trading Evolver)
- **原因**：這可以作為 AI Center 內部的基礎性能測試工具，訓練 AI 處理複雜邏輯的能力。
- **缺失節點**：Python 向量化回測容器 (VectorBT integration)。

---

## 📝 待辦事項 (Missing Nodes Checklist)
- [ ] 建立 `Sub-workflow: Core-Vision`
- [ ] 建立 `Sub-workflow: Vector-Storage`
- [ ] 實作 `Local Bridge` 處理 PS5 HID 訊號的橋接代碼
