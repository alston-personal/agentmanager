---
name: redmine_qa_workflow
description: 專屬於具備瀏覽器與公司內網存取能力節點（如 vopc5750）之 Redmine QA 測試工作流技能：涵蓋 Issue Draft 生成、HTML 預覽審查、批量 Create/Update 以及 Final Report 結案回報。
required_capabilities:
  - browser.gui
  - desktop.open_url
target_nodes:
  - vopc5750
---

# Redmine QA Workflow Skill (`capability://qa.redmine.workflow`)

## 🎯 能力邊界與節點約束 (Capability Boundary)
- **強制能力需求**：本技能嚴格要求執行節點具備 `browser.gui` 與公司內網 Redmine (`dqa02.vivotek.tw`) 連線能力（目前由 **`vopc5750`** 承接）。
- **禁止非瀏覽器節點執行**：Oracle Cloud Core 或無瀏覽器之純 Linux 備份節點不得直接執行本技能，應透過 Realm Fabric 路由派發至具備 `browser.gui` 能力之節點。

## 🚀 標準工作流 (對應 `VPP_TEST_SOP.md` 五階段閉環)
1. **Issue Draft（草稿生成）**：依實測結果與截圖證據產出結構化 Issue 草稿（New Bugs / Suggestions）。
2. **HTML Preview & Human Review Gate（預覽審查）**：產生互動式預覽 HTML 供 QA 負責人審批刪改，未獲確認前嚴禁寫入 Redmine。
3. **Create / Update（批量建單與更新）**：僅對審批通過之草稿執行 Redmine API / 瀏覽器建單或更新既有 Issue（含 Journal 結構化 HTML 修復）。
4. **Final Report & Closure（總結報告與結案）**：彙整本輪測試結果（新提單數、舊 Bug 驗證結案數）回覆測試申請母單並更新狀態為 `CLOSED`。
5. **Knowledge Inheritance（經驗沉澱）**：將本輪踩坑根因與防呆規則回寫至 `TESTING_LESSONS_LEARNED.md` 與 `VPP_TEST_SOP.md`。
