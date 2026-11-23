---
name: monthly_report
description: 兩層式跨節點工作月報生成技能：向各 node (dqa03backup, dqa03restore, vopc5750) 搜集當月公務工作切片，按 DQA Confluence 範本彙整，並於 vopc5750 啟動瀏覽器完成複製、修改與發布。
---

# Monthly Report Skill (兩層式跨節點月報統籌與發布)

## 🎯 目的
解決跨電腦多節點手動彙整月報的繁瑣流程。透過兩層架構，在主持節點（`vopc5750`）統籌派發採集任務給各 `agentos-node`，依公務白名單與 IR 比對完成資料收集，並在 `vopc5750` 叫起圖形瀏覽器，由使用者登入後自動完成 Confluence 複製、更名、填寫與發布。

---

## 🏛️ 兩層式架構設計 (Two-tier Architecture)

### 1. 上層統籌者 (Coordinator) — 運行於 `vopc5750`
* **發起入口**：使用者在 `vopc5750` 終端下達月報生成指令（可指定月份，未指定預設當月）。
* **派發搜集**：透過 ONE 控制面或節點任務向 `dqa03backup`、`dqa03restore`、`vopc5750` 派發 `monthly-report-slice` 採集任務。
* **彙整與版型套用**：
  * **本週工作重點**：摘錄當月最後一週（執行當月則為最近 7 天）之重要進行中項目。
  * **進度與狀態記錄**：依模組展開整個月已完成與進行中項目，標註 `- completed` / `- proceeding`。
* **Confluence 瀏覽器自動化**：
  * 開啟目標頁面：`https://confluence.vivotek.com/pages/viewpage.action?spaceKey=DQA&title=2026-11-24+-+DQD+Immediate+Staff+Meeting+Minutes`
  * 暫停等待使用者完成登入驗證（SSO / Active Directory）。
  * 登入後重用 Session，自動找到前一個月的 Alston 月報（11 月找 10 月，8 月找 7 月）。
  * 執行 `Copy`，更名為 `YYYY-MM-DD - Weekly Report of Alston`，修改頂部表格 Date，貼入彙整內容並點擊 `Publish`。

### 2. 下層採集者 (Collector) — 運行於各 `agentos-node`
* **公務邊界過濾 (Strict Boundary)**：白名單鎖定 DQA 公務目錄（`system`、`dqa-system`、`redmine_5`、`testrail`、維運腳本等），**嚴格排除 AgentOS / 個人研究專案**。
* **本地掃描與 IR 比對**：掃描本地 Git Commits 與維運日誌，並與本地 IR 比對產出結構化切片 (`agentos.monthly-report-slice/v1`)。

---

## 📅 發布日期計算演算法 (Date Rule)

* **核心規則**：**當月最後一個星期三（Wednesday）當週的星期五（Friday）**（注意：可能跨至下個月）。
* **計算實作**：
  ```bash
  python3 scripts/date_calculator.py [YEAR] [MONTH]
  ```
* **範例結果**：
  * 2026 年 10 月 $\to$ 最後一個週三為 10/28 $\to$ 當週週五為 `2026-10-30`
  * 2026 年 11 月 $\to$ 最後一個週三為 11/25 $\to$ 當週週五為 `2026-11-27`
  * 2026 年 12 月 $\to$ 最後一個週三為 12/30 $\to$ 當週週五為 `2027-01-01` (跨月)

---

## 📋 工具腳本一覽

1. **日期計算器**：
   ```bash
   python3 .agent/skills/monthly_report/scripts/date_calculator.py 2026 11
   ```
2. **節點切片收集器**：
   ```bash
   python3 .agent/skills/monthly_report/scripts/collect_node_slice.py dqa03backup 2026 11
   ```
3. **Confluence 範本彙整器**：
   ```bash
   python3 .agent/skills/monthly_report/scripts/format_confluence.py 2026 11
   ```
