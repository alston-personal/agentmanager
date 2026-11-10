# 🏛️ Venus Aesthetic Standard (維納斯美學與介面規格標準)

**版本:** v1.0.0 &nbsp;|&nbsp; **主管角色:** Venus (維納斯 · 美學總監) &nbsp;|&nbsp; **生效範圍:** `studio.milkcat.org` 及全域 Web 專案

---

## 💎 一、導覽系統 (Navigation System)

### 1. 拒絕橫向堆疊
* **原則**：Navbar 頂部區域絕不允許橫向平鋪超過 4 個一級按鈕，絕不允許出現因按鈕過多而造成的多行 wrap 換行混亂。
* **分組架構 (Categorical Dropdowns)**：
  1. **首頁 (Home / 3D展示)**：直接導向沉浸式場景或總入口。
  2. **連載作品 (📚 Serials)** 下拉選單：
     - 《天道敕令·阿賴耶識修真錄》
     - 《零碎證言》
     - 《AgentOS 開發血淚史》
     - 《語言迷宮的譯者》
     - 《語言雜記》/ 科技隨筆
     - Studio 完整選集
  3. **AI 實驗與工具 (🪐 Ecosystem & Tools)** 下拉選單：
     - 💧 水滴融合 (Q版生成)
     - 🪐 3D 沉浸世界
     - 🐾 石虎塔羅
     - 🎞️ If TV 電視台
     - 🧾 發票智能系統
     - 🌿 字根樞紐 & 漢字基因
     - 📊 專案看板 & 待辦總覽
  4. **右側操作區 (Action Area)**：
     - ☕ 支持我 (Support Me)
     - 🔑 登入 (Login) 彈窗觸發器 / 👤 會員面板

---

## 🔑 二、登入與認證元件 (Authentication Modal)

### 1. 獨立抽離原則
* **不外露 Provider 圖標**：禁止在 Header 直接鋪放一整排「GitHub / FB / LINE」等零碎圖標。
* **單一按鈕觸發 Modal**：
  - 未登入時：顯示典雅的「🔑 登入」按鈕。
  - 點擊按鈕：彈出半透明黑金毛玻璃風格的 `LoginModal`。
  - 登入選項支援：GitHub、Facebook、LINE 等，點擊後安全跳轉 OAuth。
* **登入後狀態**：
  - 顯示綠色狀態燈、個人暱稱或頭像。
  - 點擊展開下拉式選單：包含使用者身分、角色與登出功能。

---

## ☕ 三、支持模組 (Support Me Modal / Block)

### 1. 溫潤美感
* 取代生硬的生硬廣告，採用琥珀金色（Amber）與翡翠綠（Emerald）微光漸層。
* 清楚呈現：
  - 開源獨立維護宗旨
  - Buy Me a Coffee 專屬通道 (`https://buymeacoffee.com/registerc`)
  - 伺服器運算與演算法研發支出透明說明

---

## 🪐 四、首頁體驗 (Homepage Hierarchy)

* **主頁面 (3D 沉浸展示)**：
  - 首頁即是探索的世界，訪客可一目了然進入 3D 虛擬園區。
  - 同時提供清晰導航可快速切換至「數位文學 • 連載總覽 (Studio Archive)」。
* **無縫 iframe / 頁面切換**：
  - 點選專案時，頂部導覽列平滑保持存在，內容區平滑切換或安全外跳，避免嵌套 header 重複渲染。

---

## 🛡️ 審核強制性
任何前端修改由 Venus 進行視覺驗收。未符合上述規格者，視為介面退化，禁止發布。

