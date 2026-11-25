# 參數化基底中間層模式公理 (Parametric Base-IR Pattern, PB-IR)

- **狀態**: 已確立 (Established)
- **版本**: `agentos.axiom.pb-ir/v1`
- **適用範圍**: 全系統神祇與角色基底 (`BasePDCAWorker`, `BaseRole`)
- **核心哲學**: 幾何／物理的歸引擎，語義／決策的歸大模型。

---

## 🚫 1. 直覺陷阱 (Anti-Pattern: Raw End-to-End Simulation)
- **定義**: 試圖讓 AI 代理像人類肉眼與手指一樣，進行端到端的物理或 GUI 模擬（例如：直接看螢幕截圖操作 Blender/Paint/Premiere 介面、從頭逐像素生成、或直接刻劃 3D 頂點座標）。
- **致命傷**: 
  1. 空間幾何與時間精度感知不足；
  2. 長鏈路操作累積誤差（Compounding Error）；
  3. 狀態脆弱（彈窗或延遲即崩潰）；
  4. 算力與 Token 消耗巨大且不可重現。

---

## 💎 2. 核心公理 (The Three Core Axioms)

### 公理一：幾何／物理歸確定性引擎，語義／決策歸大模型
- 大模型專注於「理解語義、情緒、人設、架構意圖與比例關係」。
- 確定性引擎（Blender Headless `bpy`, FFmpeg, AST Parser, ControlNet, Compiler）負責「網格拓撲閉合、音視頻同步、物理碰撞與語法合法性」。
- **嚴禁強迫大模型在文字中計算空間幾何頂點或微秒時間戳**。

### 公理二：以連續參數鍵（Shape Keys / Parameters）取代離散生成
- 不讓 AI 從無到有徒手捏造結構。
- 預先定義合法邊界內的**確定性基底（Base Template / Mesh / Clean Architecture）**。
- AI 僅負責調整一組受約束的**參數鍵（Sliders / Shape Keys / Timeline Markers）**。在合法參數空間內，產出必為結構合法。

### 公理三：保留微分編輯能力（Delta Editability）
- 系統必須支援「修改 1% 需求而不推翻 99% 的既有成果」。
- 中間層 IR 必須是純文字結構化格式（JSON / YAML），支援 Git Diff 與版本控管。
- 微調角色只需修改一個參數欄位，重新觸發確定性編譯，避免重抽帶來的隨機破壞。

---

## 🏛️ 3. 眾神殿各領域投影範式

1. **美術與 3D 建模 (`ip-genome-studio`)**:
   - `Base`: 通用標準人體素體 (Parametric Base Mesh)。
   - `IR`: `Character IR` (Semantic Style + Shape Keys 0.0~2.0 + Skeleton Anchors)。
   - `Engine`: Blender 無頭腳本 (`bpy`) 編譯出標準 glTF/VRM。

2. **電影導演與剪輯 (`cine-craft`)**:
   - `Base`: 三幕劇分鏡節奏範本與標準轉場庫。
   - `IR`: `Timeline IR` (切片時間戳、鏡頭情緒、BGM 咬合點)。
   - `Engine`: FFmpeg / MoviePy 秒級無損算繪合成。

3. **編劇與世界觀架構 (`zeus-writer`)**:
   - `Base`: 小說世界觀架構與正文風格規範。
   - `IR`: `Story Arc / Chapter IR` (伏筆清單、戰力天花板、情緒節奏曲線)。
   - `Engine`: 章節生成器在安全範圍內填充散文。

4. **代碼開發與質檢 (`the_paw` / `the_claw`)**:
   - `Base`: 系統 Clean Architecture、抽象基類 (`BasePDCAWorker`)。
   - `IR`: API 契約、角色契約 (`role_contracts.json`)、Patch 描述。
   - `Engine`: Python AST、測試套件與 Doc Guard 物理驗證。
