# AgentManager 重構分析報告
> 撰寫時間：2026-03-21 UTC  
> 狀態：僅供審閱，尚未動作

---

## TL;DR

外部 Agent 提出的重構建議整體方向正確，但他**沒看到**幾個本系統已有的關鍵元件：

1. **Shared Memory (LCS Pulse Board)** — `/dev/shm/leopardcat-swarm/` 上的即時狀態廣播，已有 `pulse.py` 與 `swarm_top.py`
2. **Logic/Data 物理分離** — `symlink bridge` 架構已實施，`register_project.py` 完整落地
3. **Triple-Layer Memory Skill** — Identity / Context / Knowledge 三層架構已定義
4. **Watchdog + 事件廣播** — 已有 `watchdog.py`，且 `pulse.py` 已有 `jsonl` event log 雛形

所以問題不是「從零開始建」，而是「**升級現有基礎，補上缺失的三個核心層**」。

---

## 一、目前實際現況盤點

### ✅ 已有且運作中

| 元件 | 位置 | 狀態 |
|--|--|--|
| Logic/Data 分離架構 | symlink via `register_project.py` | ✅ 穩定 |
| `STATUS.md` per-project | `/agent-data/projects/*/STATUS.md` | ✅ 18 個專案 |
| Triple-Layer Memory | `.agent/skills/triple_layer_memory/` | ✅ 有定義，但執行面薄弱 |
| Workflow engine (手動) | `.agent/workflows/*.md` | ✅ 14 個 workflow |
| LCS Pulse Board (Shared Mem) | `/dev/shm/leopardcat-swarm/pulse.json` | ✅ 實際運行中 |
| LCS Event Log (JSONL) | `/dev/shm/leopardcat-swarm/events.log` | ✅ Append-only，已有 schema |
| Swarm Monitor TUI | `scripts/swarm_top.py` | ✅ 可用 |
| Telegram Bridge | `tg_bridge.py` + MCP server | ✅ 運行中 |
| 自動 Ecosystem Report | `run_workflow.py::run_ecosystem_report()` | ✅ 有 Telegram 推送 |
| Snapshot 機制 | `scripts/create_snapshot.py` | ✅ 可手動觸發 |
| `session_sync.md` 全域日誌 | `/agent-data/memory/session_sync.md` | ⚠️ 已 192KB，接近失控 |
| Handover Script | `scripts/handover.py` | ⚠️ 太輕薄（見下方分析） |
| `run_workflow.py` | `scripts/run_workflow.py` | ⚠️ 責任混雜，358 行 |

### ❌ 尚未建立（對照重構建議）

| 缺少的元件 | 影響 |
|--|--|
| 正式 `project.yaml` schema | `/status` 仍須 regex 解析 markdown |
| `task.yaml` schema | 無法正式追蹤 task 狀態機 |
| `session.yaml` schema | `/report` 無法結構化關閉 session |
| 結構化 event log (per-project) | 全域 LCS event log 有但 per-project 沒有 |
| `agent_core/` 模組拆分 | 業務邏輯全在 `run_workflow.py` |
| `*.yaml` machine-readable workflow | 全部只有 `*.md` 人類可讀版本 |
| Workflow registry dispatch | 目前只能 hardcode if/else |
| Session lifecycle close protocol | `/report` 只是 append summary  |
| Task state machine | 沒有 assigned/blocked/failed/handed_over  |
| Per-project event store | 只有全域 `/dev/shm/events.log`（揮發性！） |

---

## 二、對照重構建議，評估落差

### 問題 1：`run_workflow.py` 責任混雜
**外部 Agent 診斷正確。** 目前 `run_workflow.py`（358 行）同時包含：
- `load_env()`
- `send_telegram_notification()`
- Markdown regex 解析（`extract_summary_field`）
- Ecosystem report 業務邏輯（約 100 行）
- Telegram 格式化
- Subprocess dispatch
- Main router

**影響**：新增任何 action 都要動這個檔，且測試困難。

### 問題 2：Workflow 只有 `.md`，不可機器執行
**正確，但需要補充視角。** 以 `/report` 為例：
- 它的 `report.md` 只是指令說明
- `run_workflow.py` 裡的 report handler 只呼叫 `handover.py`
- 實際執行邏輯依賴 Agent 自行解讀 markdown 步驟

本系統的 workflow `.md` 原本就是「AI 閱讀後自主執行」的 SOP，不是給人類操作員用的說明書。所以「machine-readable yaml」的需求要謹慎定義——主要是為了讓 `registry` 可以 dispatch，而不是取代 md 本身。

### 問題 3：Memory 是 Markdown，可讀但不可靠
**這是目前最嚴重的現存問題。** 實際觀察：
- `session_sync.md` 已膨脹至 **192KB / 4749 行**
- 內容混雜：watchdog 警告、Telegram 即時對話紀錄、handover 摘要全部混在一起
- `create_snapshot.py` 在生成 snapshot 時會把整個 `session_sync.md` 讀進來，造成超長 context

**外部 Agent 沒看到的問題**：`session_sync.md` 同時被 `tg_bridge.py`（Telegram Agent）寫入即時對話紀錄，它已變成一個「萬用水桶」，不再有可靠語意邊界。

### 問題 4：缺少正式資料模型
**外部 Agent 診斷正確，且影響比想象中嚴重。** 目前 `run_status()` 用 regex 解析 markdown table：
```python
extract_summary_field(content, "Last Status")  # regex match markdown table row
```
這非常脆弱，格式稍有不同就會 silent fail，回傳空字串。

### 問題 5：Handover 太輕
**正確。** 現有 `handover.py`（67 行）做的事：
- 從 `SHORT_TERM.md` regex 找 pending tasks
- Append 一个手動摘要到 `session_sync.md`
- 沒有 session ID、沒有 started_at/ended_at、沒有 files_touched
- 沒有 next-agent brief 的結構化輸出

### 問題 6：缺 Task Orchestration
**正確。** 目前 task 只存在於 markdown checkbox，沒有正式的 task ID、state machine、owner、blocker。

### 問題 7：可觀測性（Observability）
**部分已有，但易失。**
- LCS Pulse `events.log` 在 `/dev/shm/`（**記憶體揮發性！重開機即消失**）
- 沒有持久化的 per-project event log
- Ecosystem report 有寫 markdown 檔，但不可查詢

---

## 三、重構優先順序建議（調整版）

外部 Agent 提出的 Phase 1-4 整體合理，但根據本系統實際現況**調整以下順序**：

### 🚨 前置緊急任務（在任何重構前必須先做）

**問題：`session_sync.md` 已 192KB，是定時炸彈**

必須先做：
1. 截斷並 archive 舊內容到 `memory/archive/`（保留最近 1000 行）
2. 建立輪替機制（超過 50KB 自動歸檔）
3. 分離 Telegram 對話紀錄（不應寫入 `session_sync.md`，應有獨立的 `telegram_sessions/` 路徑——**這個路徑其實已存在！**見 `/agent-data/memory/telegram_sessions/`）

---

### Phase 1：資料模型落地（最優先）

**目標**：建立 schema，讓 `/status` 不再靠 regex

| 任務 | 輸出 | 優先度 |
|--|--|--|
| 定義 `project.schema.json` | `rules/schemas/project.schema.json` | P10 |
| 為現有 18 個專案補 `project.yaml` | `agent-data/projects/*/project.yaml` | P9 |
| 改寫 `run_status()` 讀 yaml | `scripts/run_workflow.py` | P8 |
| 定義 `session.schema.json` | `rules/schemas/session.schema.json` | P7 |
| 建立持久化 per-project event log | `agent-data/projects/*/events.jsonl` | P7 |

**注意**：保留 `STATUS.md`，但讓它可以從 yaml 同步生成，不再作為唯一真相來源。

---

### Phase 2：拆 `run_workflow.py`（次優先）

**目標**：thin entrypoint + registry dispatch

建議目標結構：
```
agent_core/
  config.py           # 載入 .env, 路徑常數
  models.py           # ProjectState, SessionRecord, TaskRecord dataclasses
  registry.py         # action registry (decorator-based)
  renderer.py         # markdown table, telegram formatter
  errors.py           # 統一 exception

actions/
  status.py           # run_status() 搬過來
  ecosystem_report.py
  snapshot.py
  report.py
  register_project.py # 升級版

cli/
  run_workflow.py     # 只剩 parse + dispatch + exit code (~50 行)
```

**可漸進遷移**：每次新增 action 直接放到 `actions/`，舊的逐步搬移，不需停機。

---

### Phase 3：升級 `/report` 成正式 Session Lifecycle Protocol

**目標**：`/report` = close session + emit handover document

新的 `/report` 應執行：
1. 生成 `session_id`（UUID）
2. 讀取 `project.yaml` 確認 project 資料
3. 萃取本次完成的 tasks，更新 task status
4. 寫入 `sessions/YYYY-MM-DD_<session_id>.yaml`
5. 更新 `project.yaml` 的 `updated_at` 與 `current_focus`
6. 結構化生成 `next_agent_brief`（pending tasks + context）
7. Append **精簡版** handover 到 `session_sync.md`（不再 dump 全文）
8. 送 Telegram 通知
9. 寫入 `events.jsonl`（event_type: `session_closed`）

---

### Phase 4：Workflow Machine-Readable 化（最後）

**目標**：為每個 workflow 補 `*.yaml` 格式

这是工程複雜度最高的 Phase，但**目前收益相對最低**（AI Agent 本來就能讀 `.md`）。

建議策略：
- 先建立 yaml workflow schema 定義
- 只為最常用的 4 個 workflow 補 yaml：`/report`、`/status`、`/register-project`、`/snapshot`
- 不急著全部補完

---

## 四、本系統特有資產，重構中必須保留

外部 Agent 建議沒提到，但**一定不能在重構中破壞**的元件：

| 資產 | 重要性 | 備註 |
|--|--|--|
| **LCS Pulse Board** (`/dev/shm/pulse.json`) | 極高 | 多 Agent 即時協作的核心，需要補持久化副本 |
| **LCS Event Log** (`/dev/shm/events.log`) | 高 | 揮發性！需要持久化到 `agent-data` |
| **Symlink Bridge** (STATUS.md, memory/) | 極高 | 邏輯/資料分離的實體保證，不能動 |
| **Telegram Push** (tg_bridge.py + MCP) | 高 | 完整自主感知迴路的一環 |
| **Watchdog** (scripts/watchdog.py) | 高 | 目前唯一的主動監控機制 |
| **Triple-Layer Memory Skill** | 中 | 需搭配 session.yaml 強化，但定義本身保留 |

---

## 五、逐條回應「成功標準」

| 成功標準 | 目前狀態 | 重構後目標 |
|--|--|--|
| 任一 agent 進場可讀結構化 project/task/session | ❌ 只有 markdown | ✅ `project.yaml` + `session.yaml` |
| `/report` 可穩定關閉 session 並產生 handover | ⚠️ 只有 append summary | ✅ Session lifecycle close protocol |
| `/status` 由 structured schema 生成 | ❌ regex markdown | ✅ 讀 `project.yaml` |
| Workflow 可被 registry dispatch | ❌ hardcode if/else | ✅ registry-based |
| 所有重要動作寫入 event log | ⚠️ 只有 LCS (揮發性) | ✅ 持久 `events.jsonl` |
| Markdown 仍保留供人類閱讀 | ✅ 有 STATUS.md | ✅ 保留，但改為由 yaml 同步生成 |

---

## 六、不建議現在動的事

1. **廢棄 `session_sync.md`** — 目前是 Telegram Agent 的寫入目標，貿然廢棄會破壞 tg_bridge 記憶通道
2. **廢棄 `.md` workflow** — AI Agent 本來就能讀 md，yaml 的優先度低於 schema 落地
3. **一次性大重構** — 系統目前在日常使用中（tarot、openclaw CI 等），不能停機重構

---

## 七、建議的第一個動作

如果確認要推進，第一個動作建議是：

> **建立 `project.yaml` schema + 補 2-3 個示範專案的 yaml 檔**

驗證讀取邏輯可行，再逐步鋪開到所有 18 個專案。

這個動作：
- 風險最低（不改任何現有程式碼）
- 收益最大（解決 `/status` 的 fragility 問題）
- 可以漸進（先 2-3 個專案試）

---

*此文件為分析記錄，待 Alston 確認後再決定實際執行計畫。*
