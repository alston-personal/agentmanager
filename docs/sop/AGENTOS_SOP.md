# AgentOS Standard Operating Procedures (SOP)
**版本**：v1.0 (2026-11-09)  
**文件定位**：全生態系統治理、Agent 自主執行、多角色協作與人機交互之最高標準作業程序。

---

## 零、 核心基石：接力棒無殘留協議 (Zero-Residual Baton Protocol)

> **最高原則**：  
> **所有中繼點資料產生或接手後，必須將其使用到乾淨（終態消費），或是明確交接給下一手；下一手遞迴遵循相同原則，直到達成完全終態。絕不允許產生任何無人處理、懸空堆積的資料。**

### 1. 接力棒三態定律
1. **生成必有歸屬 (No Orphan Birth)**：
   - 任何腳本、排程、LLM 或 Agent 產出中繼資料（日誌、報告、候選特徵、代碼草稿、問題清單）時，必須在元數據中明確綁定消費者（Consumer）或目標隊列。
   - 若無明確下游接手者，該程序**禁止執行無意義產出**。
2. **接手必達終態 (Consume to Terminal State)**：
   - 接手者對手中的資料負全責，僅有兩條合法退出路徑：
     - **路徑 A（就地終結消費）**：修復了問題、驗證了代碼、將原始零碎日誌壓縮結算為指標並清理原始檔、或判定無須行動並顯式註記理由封存。
     - **路徑 B（顯式移交下一手）**：若需跨角色/跨模組協同，必須將結構化工單派發給特定的下一手負責人，並取得隊列收錄確認（ACK）。
3. **違規熔斷 (Breakpoint Violation)**：
   - 任何中繼資料在磁碟或隊列滯留超過生命週期上限（TTL）且無 Active Owner 認領，視為系統斷鏈。System Sentinel 必須阻斷上游生產者並發出 P0 告警，嚴禁無聲積累。

---

## 一、 會話啟動與延續 SOP (Session Initiation & Bootstrap SOP)

### 1. 識別環境與權威延續性
- **物理中心**：
  - 邏輯層 (Logic)：`/home/ubuntu/agentmanager`
  - 真相層 (Data)：`/home/ubuntu/agent-data`
- **權威狀態判定**：
  - 當新對話或 Agent 啟動時，唯一權威延續性來自 **AgentOS ONE Canonical IR**（包含 `project_id`、`index_id`、`ir_id`、`executor_class`）。
  - **嚴禁**依賴 IDE 當前開啟的工作區路徑、舊對話歷史、或本地記憶隨意推測上下文。

### 2. 專案身份驗證 (Fail-Closed)
- Agent 進入任何專案前，必須呼叫 `one_resolve` 或驗證該專案在治理註冊表（`agent_core/project_store.py`）中合法存在。
- **Fail-Closed 門禁**：若無法解析專案 ID，嚴禁在 `agent-data/projects/` 下以 Hash 或臨時字串自動 `mkdir` 建立幽靈目錄。

### 3. 軟連結橋樑 (The Symlink Bridge) 檢測
- 進入任何專案代碼目錄，必須確認以下軟連結有效：
  - `STATUS.md` $\rightarrow$ `/home/ubuntu/agent-data/projects/[project-name]/STATUS.md`
  - `memory/` $\rightarrow$ `/home/ubuntu/agent-data/projects/[project-name]/memory/`
- **禁止覆寫軟連結**：嚴禁刪除軟連結改為實體檔案，嚴禁將數據直接提交至代碼倉庫。

---

## 二、 任務流轉與生命週期 SOP (Task Lifecycle & Dispatch SOP)

### 1. 任務進入隊列標準
- 所有進入 `$AGENT_DATA_ROOT/GLOBAL_TODO_LIST.md` 或 `$AGENT_DATA_ROOT/TASK_BOARD.md` 的任務，必須遵循 [`docs/TASK_SPECIFICATION_STANDARD.md`](file:///home/ubuntu/agentmanager/docs/TASK_SPECIFICATION_STANDARD.md)：
  - **明確邊界**：指出受影響的檔案路徑或模組名稱。
  - **執行前置 (Pre-requisite)**：指明前置條件是否滿足。
  - **明確驗收閘門 (Acceptance Gate)**：必須附帶可自動執行的驗收指令（例如：`pytest tests/test_xxx.py` 或 `test -f ...`），嚴禁抽象空泛的純文字佔位符（如「定義目標」、「規劃架構」）。

### 2. 任務認領與排他性
- 執行器（如 Lobster、Role PDCA Worker）認領任務前，必須向 **Work Completion Ledger** 註冊租約（Claim Lease），標記當前 generation 與 owner，防止多 Agent 同時衝突修改。

### 3. 任務執行與日誌清潔
- 任務執行產生的過程日誌，嚴格遵循「接力棒原則」：
  - 任務成功：提取關鍵指標（耗時、改動檔案清單）回寫 `STATUS.md`，清理非必要的臨時 debug 日誌，避免磁碟小檔案暴增。
  - 任務失敗：記錄失敗原因與錯誤碼；若連續 3 次失敗，**必須觸發阻斷並升級通知**，禁止無限靜默重試。

---

## 三、 代碼變更與發布審批 SOP (Mutation & Protected Branch SOP)

### 1. 受保護分支不可侵犯
- 針對 `main`、`master`、`release/*`：
  1. Agent 只能在獨立 Feature / Fix 分支建立變更。
  2. Agent 產出代碼、測試與 Pull Request 後，僅能標記為 `READY_FOR_MERGE`。
  3. **必須停留在 `AWAITING_HUMAN_APPROVAL`**，嚴禁擅自直接 push 或自動 merge。
  4. CI 成功、測試通過或用戶普通的「繼續」指令，**均不代表合併授權**；必須有明確的人類審批命令（如「批准合併」）。

### 2. 文件真實性守衛與原子同步法則 (Atomic Doc-Code Parity Law)
- **核心鐵律**：**動 Code 必動 Doc，代碼與說明文件互為原子一體。未同步更新文檔的代碼視為未完工殘品。**
- **三道剛性保險**：
  1. **第一道（日常運作態 / PDCA 驗收）**：
     - Paw (工匠) 在完成實作前，必須同步更新架構與接口說明文件。
     - Claw (審計官) 在 Check 階段主動執行 `python3 scripts/documentation_reality_guard.py --worktree`，若發現代碼變更但文檔未更新，**直接判定 FAIL 打回重做**，不予結案。
  2. **第二道（本地提交態 / Pre-Commit 攔截）**：
     - 每次執行 `git commit` 時，[`.agent/scripts/pre_commit_guard.sh`](file:///home/ubuntu/agentmanager/.agent/scripts/pre_commit_guard.sh) 強制執行 `python3 scripts/documentation_reality_guard.py --staged`。
     - 暫存區中若只有代碼修改而無權威說明文件更新，提交當場被物理拒絕。
  3. **第三道（分支合併態 / CI 門禁）**：
     - GitHub Actions CI 嚴格校驗 `--base origin/main`，禁止文檔脫節的 PR 合併入受保護分支。
- 權威說明文件包含：`README.md`、`docs/CURRENT_STATE.md`、`ONBOARDING.md`、`AGENTS.md`。
- 變更驗收指令：
  ```bash
  python3 scripts/documentation_reality_guard.py --worktree
  python3 scripts/documentation_reality_guard.py --staged
  python3 scripts/continuation_state.py --self-test
  ```

---

## 四、 巡檢自癒與資料終態 SOP (Sentinel & Terminal Sinks SOP)

### 1. 每日冥想 (Meditation) 閉環規範
- [`scripts/meditation/meditator.py`](file:///home/ubuntu/agentmanager/scripts/meditation/meditator.py) 生成系統反思與架構升級建議後，**不得停留在單純寫入 Markdown**：
  - 輸出建議必須即時解析，提取出最具體的一項行動派發至看板隊列，指定負責 Persona 接手。
  - 若評估當前無須架構變更，必須標記為 `TERMINAL_DISCARD (Reviewed, No Action Required)`，做到每一份思維產出均有終態結論。

### 2. 品質巡檢 (Quality Sentinel) 閉環規範
- 巡檢發現異常（字數不足、代碼違規、格式錯誤）：
  - 自動生成指向責任角色的修復 Work Item 並排入隊列。
  - 下次巡檢時，若問題修復則將該 Work Item 銷毀結案；若問題連續存在，升級為系統阻斷事件。

### 3. 歷史日誌自動滾動 (Log Compaction & Pruning)
- 定期執行壓縮腳本，將超過 7 天的歷史 Task Log 聚合為日/週摘要指標，刪除單次執行的小檔案，保持 inode 與磁碟健康。

---

## 五、 雙軌身心合一與受控演進 SOP (Dual-Track Mind-Body Parity SOP)

### 1. 軌道一：核心治理層（憲法與 Agent Rules）—— 永恆身心合一 (Strict Immediate Parity)
- **最高天條**：凡是寫入憲法 (`.agent/CONSTITUTION.yaml`) 與核心規則 (`.agent/AGENT_RULES.md`) 的條文，**必須在同一個變更集中具備物理代碼守門 (Guards)、執行期阻斷或 Git 門禁**。
- **嚴禁純口號**：尚未以代碼物理落實的規範，只能列為「指導方針 (Guideline / Policy Guidance)」，嚴禁列為核心不變量（Immutable Invariant）欺騙系統。
- **動 Rule 必動 Guard，動 Guard 必動 Rule**，兩者互為原子一體。

### 2. 軌道二：應用與專案層（Projects & Features）—— 受控誠實四態標準 (Honest 4-State Lifecycle)
- **研發週期合規性**：專案開發允許存在「已發想、規格設計中、待實作」的合理時間差，但**必須在嚴格受控下誠實標註狀態**：
  1. `💡 Proposed (已發想 / 待排期)`：規格明確、目標專案明確、Acceptance Criteria 確立。實作路徑誠實標示為待辦，由 Spec Steward 追蹤新鮮度與依賴關係。
  2. `🔨 In-Progress (實作中)`：已認領進入當前 Sprint，實施進度即時記錄於 `STATUS.md`。
  3. `✅ Implemented / Verified (已實裝且通過驗收)`：
     - **剛性鐵律：必須同時具備【實體代碼路徑】+【可重複執行的測試指令或 Receipt 憑證】！**
     - **嚴禁未落實但文件已標示完成 (Zero Tolerance for False Completion)**。只要缺少真實代碼或測試未通，一律強制降級回 `Proposed` 或 `In-Progress`。
  4. `📦 Closed / Archived (已閉環 / 已歸檔)`：實作交付上線後，原始 Spec 必須顯式標註 `status: closed`、`closed_at: <DATE>` 與 `resolution: <PATH>`，正式結案交割，不得長期懸空。

### 3. 物理守護與門禁整合 (Physical Guards & Gates)
- **日常運行態 (Claw & PDCA)**: `ConstitutionKeeperWorker` 與 `SpecStewardWorker` 自動執行 `python3 scripts/spec_steward.py --check`，一旦發現任何宣稱完工卻有未完成項之規格，直接判處 `FAIL` 打回。
- **提交前門禁 (Pre-commit)**: Git hook 強制執行 `scripts/documentation_reality_guard.py --staged`。
- **合併門禁 (CI & Protected Branch)**: CI 執行 `documentation_reality_guard.py --base origin/main`，杜絕任何身心脫節變更進入主線。
