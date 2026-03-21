# 🗂️ AgentManager 架構現況報告 + 行動計畫
> 撰寫時間：2026-03-21 UTC  
> 目的：給 Alston 明天醒來時快速掌握全局，接續推進重構計畫  
> 撰寫者：Antigravity（本次對話 AI）

---

## 📌 為什麼其他 Agent 讀 repo 會漏掉東西？

**答：因為最關鍵的三個系統都不在 repo 裡。**

| 漏掉的東西 | 實際位置 | 為何外部 Agent 看不到 |
|--|--|--|
| **LCS Pulse Board（Shared Memory）** | `/dev/shm/leopardcat-swarm/pulse.json` | `tmpfs`，不 commit，重開機即消失 |
| **LCS Event Log** | `/dev/shm/leopardcat-swarm/events.log` | 同上，揮發性記憶體 |
| **Process 運行狀態** | `systemd --user` service + `pulse.py` PID tracking | 只是執行態，不是文件 |

所以外部 Agent clone repo → 只看到骨架，**看不到任何 runtime 狀態**。
這是架構設計的雙面刃：分離很乾淨，但入場的 Agent 需要主動偵測環境。

---

## 🏗️ 目前實際落地狀況（2026-03-21 盤點）

### ✅ 已 commit（HEAD: `ae18204`）的新元件

上一次重構對話（`1558b386`）已在本地 commit（**但尚未 push**）以下內容：

```
agent_core/__init__.py
agent_core/config.py         ← 路徑常數、環境變數載入
agent_core/models.py         ← ProjectRecord / SessionRecord / TaskRecord / EventRecord dataclasses
agent_core/project_store.py  ← load_project / save_project / list_projects / emit_event
scripts/init_project_yaml.py ← 批次從 STATUS.md 生成 project.yaml
rules/schemas/project.schema.json  ← JSON Schema (完整)
rules/schemas/session.schema.json  ← JSON Schema
rules/schemas/task.schema.json     ← JSON Schema
REFACTOR_ANALYSIS.md         ← 現況分析（你已有）
```

**這是 Phase 1 的骨架已完成！** 但未 push，外部 Agent 看不到。

### ✅ 更早就運作中的元件

| 元件 | 狀態 |
|--|--|
| LCS Pulse Board (`pulse.py` + `swarm_top.py`) | ✅ 運行中（`/dev/shm/leopardcat-swarm/pulse.json`） |
| Swarm Monitor TUI (`swarm_top.py`) | ✅ 可用 |
| Watchdog (`watchdog.py`) | ✅ systemd service 監控 |
| Telegram Bridge (`tg_bridge.py`) | ✅ 運行中 |
| Symlink Bridge (Logic/Data 分離) | ✅ 穩定（`register_project.py` 負責） |
| 18 個專案的 `STATUS.md` | ✅ 存在於 `/agent-data/projects/*/` |
| Ecosystem Report（自動 Telegram 推送） | ✅ |
| Triple-Layer Memory Skill 定義 | ✅ 有 SKILL.md，執行面待補強 |

### ⚠️ 現存緊急問題

**`session_sync.md` 已失控：**
- 大小：`~192KB / ~4749 行`（上次測量值）
- 問題：Telegram 對話、watchdog 警告、handover 摘要全混在一起
- 風險：`create_snapshot.py` 會把整個檔讀入 context，造成 context 爆炸

### ❌ 仍未落地的元件

| 缺少的 | 影響 |
|--|--|
| 18 個專案的 `project.yaml` 尚未生成 | `init_project_yaml.py` 已寫好但未執行 |
| `sessions/*.yaml` per-session 記錄 | `/report` 仍是 append-only |
| `tasks/*.yaml` 正式 task 狀態機 | task 仍只是 markdown checkbox |
| 持久化 per-project `events.jsonl` | 全域 LCS event 揮發，per-project 沒有 |
| `/report` Session 正式關閉協議 | `handover.py` 只有 67 行，無 session_id、無 files_touched |
| Workflow registry dispatch | 仍是 `run_workflow.py` 裡的 hardcode if/else |
| `run_workflow.py` 拆分 | 仍是 398 行的大鍋炒 |
| Process runtime 正式定義 | `pulse.py` 有 PID，但沒有正式 spawn/fork/kill API |

---

## 🧠 對你補充的三個核心概念的分析

你說還有 **shared memory**、**process 化**、**去 IDE 化** 三個重要能力尚未 commit 完整。
以下是我看完目前 repo 後的判斷：

### 1. Shared Memory（LCS Pulse Board）

**目前落地程度：60%**

- ✅ `/dev/shm/leopardcat-swarm/pulse.json` — 即時 heartbeat，已運作
- ✅ `/dev/shm/leopardcat-swarm/events.log` — append-only JSONL event bus
- ✅ `swarm_top.py` — TUI 監控，已可用
- ❌ **揮發性問題未解**：全部在 `/dev/shm`，重開機歸零
- ❌ **沒有 ownership / scope / locking**：多 agent 同時寫 pulse.json 沒有並發控制
- ❌ **沒有 Memory Contract 文件**：哪些是 global memory，哪些是 project-scoped，哪些是 agent-private，沒有定義

**最小可行修復**：每次 pulse 更新同時 sync 一份到 `agent-data/runtime/pulse_snapshot.json`，解決揮發性問題。

### 2. Process 化

**目前落地程度：30%**

- ✅ `pulse.py` 有 `pid` 欄位 — 知道 agent 的 PID
- ✅ `watchdog.py` 有 systemd service 監控 + 重啟邏輯
- ❌ **沒有 process registry**：agent 不知道自己是否已有另一個 instance 在跑
- ❌ **沒有 spawn/fork API**：目前都是手動執行 script，沒有程式化的 agent 生成機制
- ❌ **沒有 IPC (Inter-Process Communication)**：agents 目前靠 shared file（pulse.json）間接溝通，沒有真正的 message passing
- ❌ **沒有 process identity**：fork 出來的 agent 沒有正式 ID、父子關係、任務分配記錄

**最關鍵的缺口**：Agent 之間現在完全靠「同一台機器上摸同一個檔案」溝通。這能用，但不是真正的 IPC。

### 3. 去 IDE 化（IDE-Decoupled Runtime）

**目前落地程度：50%**

- ✅ Telegram Bridge — 完全獨立於 IDE，agent 可透過 TG 接收指令
- ✅ `systemd --user` service — tg-commander 是常駐 process
- ✅ MCP server 在 `servers/` — OpenClaw 有 multi-channel 通訊能力
- ❌ **沒有 unified command API**：IDE 版（run_workflow.py CLI）和 Telegram 版（tg_bridge.py）是兩套完全獨立的指令處理邏輯
- ❌ **沒有 session context portability**：IDE session 結束，context 就 lost（handover 太弱）
- ❌ **沒有 agent 身份系統**：不同 channel（IDE、TG、CLI）的 agent 沒有統一身份 schema

---

## 🗺️ 調整後的行動計畫（最新版）

在你昨天（`REFACTOR_ANALYSIS.md`）的 Phase 1-4 基礎上，加入對上述三個核心概念的補強：

### 🚨 緊急：在任何重構前先做

**任務：截斷 `session_sync.md`**
```bash
# 保留最後 500 行，舊的 archive
tail -500 /home/ubuntu/agent-data/memory/session_sync.md > /tmp/sync_tail.md
cp /home/ubuntu/agent-data/memory/session_sync.md /home/ubuntu/agent-data/memory/archive/session_sync_$(date +%Y%m%d).md
mv /tmp/sync_tail.md /home/ubuntu/agent-data/memory/session_sync.md
```
**風險**：零。舊記錄已 archive，不刪，只截斷作用中的檔案。

---

### Phase 1：資料模型落地（已 90% 準備好，只差最後一步）

**已有**：`agent_core/models.py`、`project_store.py`、所有 schema JSON、`init_project_yaml.py`

**下一步**：
```bash
# 執行批次生成所有 project.yaml（dry-run 先看）
python3 scripts/init_project_yaml.py --dry-run
# 確認 ok 後
python3 scripts/init_project_yaml.py
```
這一個指令完成後，`/status` 就可以從 yaml 讀取，不再靠 regex 解析 markdown。

**後續**：Push `ae18204` commit 讓所有 Agent 可見。

---

### Phase 1.5：補 Shared Memory 持久化（新增）

**任務**：解決 `/dev/shm` 揮發性問題

建議路徑：
- `agent-data/runtime/pulse_snapshot.json` — 每次 `update_pulse()` 同時寫入持久化副本
- `agent-data/runtime/events_archive/YYYY-MM-DD.jsonl` — 每天 rotate，持久化 event log

改動地點：`scripts/pulse.py` 的 `update_pulse()` 和 `log_event()` 加兩行寫入 agent-data 副本。

---

### Phase 2：拆 `run_workflow.py`（可漸進，不需停機）

建議策略：
1. 先把 `send_telegram_notification` 和 `format_telegram_report` 搬到 `agent_core/renderer.py`
2. 把 `run_ecosystem_report()` 搬到新建的 `actions/ecosystem_report.py`
3. 主 entrypoint 留 `cli/run_workflow.py`，import actions
4. 每次新 action 直接在 `actions/` 建新檔，不動原始 run_workflow.py

**不需要一次全部重寫。**

---

### Phase 3：升級 `/report`（最重要的業務邏輯升級）

新的 `report.py` action 應該做：
1. 生成 `session_id = uuid4()`
2. 讀取當前 project 的 `project.yaml`
3. 萃取完成的 tasks（從 SHORT_TERM.md checklist）
4. 寫入 `agent-data/projects/{project}/sessions/{date}_{session_id}.yaml`
5. 更新 `project.yaml` 的 `updated_at`、`health.freshness`、`current_focus`
6. 寫入 `agent-data/projects/{project}/events.jsonl`（event: `session_closed`）
7. 只 append 一行精簡 handover 到 `session_sync.md`（不再 dump 全文）
8. 送 Telegram 通知

---

### Phase 4：Process Runtime 正式定義（新增，對應你的「process 化」願景）

這是最有潛力但也最需要謹慎的部分。

最小可行版：
- 定義 `agent-data/runtime/processes.json`：
  ```json
  {
    "agents": {
      "tg-commander": { "pid": 12345, "started_at": "...", "channel": "telegram", "status": "active" },
      "ide-gemini": { "pid": 67890, "started_at": "...", "channel": "ide", "status": "active" }
    }
  }
  ```
- `pulse.py` 在 `update_pulse()` 時同步更新此檔
- 定義 `agent identity`：每個 agent session 有 `agent_id`（uuid），可被其他 agent 引用

**暫不實作** fork/spawn API，先補好 identity + registry，再考慮 spawn。

---

### Phase 5：Workflow Machine-Readable 化（最後，優先度相對最低）

只為 `/report`、`/status`、`/register-project`、`/snapshot` 補 yaml。
其他 workflow 仍維持 `.md` 格式（AI Agent 能讀 md 就夠）。

---

## 📊 成功指標更新版

| 標準 | 現況 | Phase 完成後 |
|--|--|--|
| Agent 進場可讀結構化 project context | ❌ | ✅ `project.yaml` 全面落地後 |
| `/status` 不靠 regex | ⚠️ 已有 fallback 邏輯 | ✅ init_project_yaml 執行後即可 |
| `/report` 正式關閉 session | ❌ | ✅ Phase 3 後 |
| Shared memory 不揮發 | ❌ | ✅ Phase 1.5 後 |
| Agent 有正式 process identity | ❌ | ✅ Phase 4 後 |
| 其他 Agent 讀 repo 不漏掉東西 | ❌ | ✅ Push + runtime 文件化後 |

---

## 💡 一句話給明天的 Alston

> 你不是從零開始。你已經有 60% 的架構落地了。  
> 現在最需要的不是繼續設計，而是**執行三個具體命令**：  
> 1. `git push`（讓 ae18204 對其他 Agent 可見）  
> 2. `python3 scripts/init_project_yaml.py`（讓 `/status` 用 yaml 驅動）  
> 3. 截斷 `session_sync.md`（解除定時炸彈）  
> 
> 這三件事做完，整個系統的基礎就穩了，之後再逐步推進 Phase 2-4。

---

*此文件由 Antigravity 撰寫，基於 2026-03-21 16:13 UTC 的 repo 現況分析。*
*對應對話：`1558b386`（上次）、`c0760099`（本次）*
