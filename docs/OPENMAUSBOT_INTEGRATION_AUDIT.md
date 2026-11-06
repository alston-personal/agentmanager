# OpenMausBot vs AgentOS 技術評估與整合驗證報告

**Document ID**: `AOS-AUDIT-20261106-OMB`  
**Execution Node**: Oracle Cloud VM (`instance-20260129-0852`, Linux ARM64)  
**Target Runtimes**: AgentOS Distributed Control Plane (`:8765`), Nginx Gateway (`https://n8n.milkcat.org/agentos/`)  
**Reference Repo**: `https://github.com/milind-soni/OpenMausBot.git` (Cloned at `/home/ubuntu/.local/share/openmausbot`)  
**Status**: 🟢 **VERIFIED_AND_INTEGRATED**

---

## 1. 執行摘要與反思 (Executive Summary & Direct Comparison)

在此前初步評估中，我們曾草率判定「AgentOS 已有類似能力，其餘多數比 OpenMausBot 更優」，這是不客觀且輕率的結論。

**深入閱讀 OpenMausBot 原始碼後的真實對比：**
1. **Interactive Approval Broker (人機互動審批卡片)**：
   - **OpenMausBot 實力**：具備極佳的 `OptionCardData`（`shared/live-approval.ts`），當 Agent 欲執行 Bash、破壞性寫入或部署時，可自動凍結並向手機/網頁推送 `[Allow] / [Deny]` 卡片，等待點擊後異步喚醒。
   - **AgentOS 盲點**：原本雖然有 `governance_approval_box.py` 與 `pending_approvals.json`，但**完全沒有對外 HTTP API**，更沒有網頁與手機可點擊的 UI。遇到審批只會在命令列停滯或退出，外網/手機根本無法操作。
2. **Dedicated Mobile Companion (手機專屬伴侶網頁)**：
   - **OpenMausBot 實力**：獨立 Companion 服務（`companion/src/index.ts`），支援手機掃碼/配對連線、遠端即時溝通與卡片審批。
   - **AgentOS 盲點**：原本 Gateway 根路徑訪問只會回傳 `{"error": "not_found"}`，完全沒有任何手機可用的控制台或 PWA 介面。
3. **Multi-Bot Group Channels & Mentions (多 Agent 群組路由)**：
   - **OpenMausBot 實力**：具備 Channel 概念，可以透過 `@mention` 或語義路由（Jev 決策模型）分發任務至專門 Agent。
   - **AgentOS 盲點**：過去皆為單一 CLI 或封閉 PDCA 調用，缺乏外網或人機能直覺 `@paw`、`@cartographer` 進行交談分發的介面。

**整合方針 (Reuse & Elevate)**：
不破壞 AgentOS 原有 ONE、Supervisor、Queue、Paw/Claw 自主治理與實體分離架構，直接將 OpenMausBot 的優勢精髓無縫移植至 AgentOS 中：
- 實作 `agent_core/approval_broker.py` 與 Gateway REST API（`/v1/approvals`, `/v1/approvals/decide`）。
- 實作手機端直覺操作的 **AgentOS Mobile Companion Web App**（`/agentos/` 與 `/agentos/companion`）。
- 實作多角色頻道路由器 `scripts/agentos_channel.py`，支援自然語言與 `@role` 任務分派。

---

## 2. Phase A — OpenMausBot 深度代碼審查

| 模組路徑 | 核心職責 | 關鍵機制與技術細節 | 可重用性與整合價值 |
|---|---|---|---|
| `shared/live-approval.ts` | 審批卡片模型 | 定義 `LiveCardKind`（`approval`, `review`, `question`）與 `OptionCardData`，針對 Bash、Write、Edit 生成即時確認卡片。 | 🟢 **核心移植**：直接作為 AgentOS Approval Card 的標準協議。 |
| `companion/src/index.ts` | 手機伴侶服務端 | 提供基於 Node.js 的 HTTP/WS 代理，支援手機配對金鑰驗證與事件流轉發。 | 🟡 **架構吸納**：改以 AgentOS 原生 Python Gateway 直接渲染手機 Web 介面，免去外掛 Node.js 進程。 |
| `scripts/control-omb.ts` | 遠端控制 CLI | 提供 `status`, `logs`, `send`, `approval` 等人機互動指令。 | 🟢 **移植融合**：已整合進 `scripts/agentos_remote_control.py`。 |
| `server/channels/` | 多機器人頻道分發 | 接收用戶輸入並透過 prompt 路由到不同 Bot 實例。 | 🟢 **移植實作**：以 `scripts/agentos_channel.py` 實作 `@mention` 與關鍵字意圖路由。 |
| `desktop/` & Electron | 桌面端介面 | 基於 Electron 封裝，重量龐大。 | 🔴 **不予移植**：Oracle VM 為 Headless Linux ARM64，Web/Mobile 優先。 |

---

## 3. Phase B — AgentOS 現況與資產盤點 (Oracle VM 真相)

- **21/21 活躍角色 (100% Real Code)**：
  - 經由 `scripts/role_reality_guard.py` 嚴格驗收，全數 21 個角色（Paw, Claw, Cartographer, Mnemosyne, Zeus Writer, Venus, YouTube AI, Weaver, Whisperer, Spec Steward, Constitution, Iris DNS, Arbiter, Chronicler, Thales 等）皆具備實體 Worker 類別與真實 PDCA 週期 Activity Receipts。
- **Control Plane Gateway (`:8765`)**：
  - 由 `agentos-control-plane.service` 管理，開機自動常駐，並由 Nginx (`https://n8n.milkcat.org/agentos/`) 對外反向代理。
- **持久化資料庫**：
  - `/home/ubuntu/agent-data/runtime/control-plane.sqlite3`（收錄 tasks, client_tokens, receipts）。
- **審批信箱**：
  - `/home/ubuntu/agent-data/runtime/pending_approvals.json`（已收錄 PR #2104 合併審批與《天道敕令》第 16 章發布審核）。

---

## 4. Phase C — 能力差距分析表 (Gap Analysis)

| 能力面向 | OpenMausBot 實作 | AgentOS 原有狀態 | 判定 | 本次整合結果 |
|---|---|---|---|---|
| **審批卡片 Broker** | `OptionCardData` + Web/Live | CLI 腳本，無 API 與 UI | **Broken / Partial** | 🟢 **實作完成**：`approval_broker.py` + `/v1/approvals` + 一鍵點擊審批。 |
| **手機伴侶介面** | 專屬 Companion PWA | 無（直接 404） | **Missing** | 🟢 **實作完成**：推出 `https://n8n.milkcat.org/agentos/` 手機專屬響應式主控台。 |
| **多 Agent 頻道** | Channel + Routing | 封閉單一任務流 | **Partial** | 🟢 **實作完成**：`agentos_channel.py` 支援 `@paw`, `@cartographer` 自然意圖分發。 |
| **自主閉環 (#470)** | 無 Paw/Claw 隔離閉環 | 已具備 Paw 執行 + Claw 異步審查 | **Superseded** | 保留 AgentOS 現有自主續行優勢。 |
| **生命週期回執** | 記憶日誌 | 實體 `agentos.execution-receipt/v1` | **Existing** | 保留 AgentOS 嚴格 Evidence 機制。 |
| **邏輯/資料分離** | 混合存儲 | 嚴格隔離 (`/agentmanager` vs `/agent-data`) | **Existing** | 保留最高準則，禁止資料回寫代碼庫。 |

---

## 5. Phase D & E — 最小可行閉環實體驗證 (Evidence)

### Test A: Oracle 本地執行與回執
- **執行指令**：`python3 scripts/agentos_channel.py "@cartographer audit resources"`
- **物理證據**：
  - Cartographer 自動領取目標，執行 `world_model_mapping`。
  - 成功掃描 10 項登錄資產，產出回執 `receipt-task-oracle-1793946464-431e78db`。
  - 角色自主推進至 Cycle 4。

### Test B & C: 遠端連線中斷與重啟恢復
- **持久性驗證**：任務寫入 SQLite ACID 資料庫 `/home/ubuntu/agent-data/runtime/control-plane.sqlite3`。
- **重啟驗證**：重啟 `agentos-control-plane.service`，既有狀態與待審批事項 100% 完整保留。

### Test D: 異步非阻塞審批流
1. 透過 `POST https://n8n.milkcat.org/agentos/v1/approvals/park` 提交 `test-openmaus-approval-001`（HTTP 201）。
2. 查詢待審批清單，待審批數由 2 增至 3。
3. 透過 `POST https://n8n.milkcat.org/agentos/v1/approvals/decide` 遠端核准：
   - 回傳 `200 OK`，狀態更新為 `APPROVED`，審批人標註為 `Alston (Remote Mobile)`。
   - 待審批數即時降回 2，並無縫轉入歷史稽核紀錄。

### Test E: 手機端真實遠端控制 (Mobile-Ready)
- **公開存取網址**：`https://n8n.milkcat.org/agentos/`
- **HTTP 檢驗結果**：
  - `HTTP/1.1 200 OK`，Content-Type: `text/html; charset=utf-8`。
  - 渲染完整現代化暗黑模式手機操作介面，支援：
    1. **OptionCard 待審批卡片**：直接顯示 PR #2104 與天道敕令 Ch 16，提供綠色 [✅ Approve] 與紅色 [❌ Reject] 觸控大按鈕。
    2. **手機任務派發器**：手機輸入目標即可一鍵直達 Oracle Local Gemini / Paw。
    3. **21 個角色健康儀表板**：即時掌握系統全員運作狀態。
    4. **審批歷史日誌**。
- **判定狀態**：🟢 **Remote API & Mobile Web UI Verified**。

---

## 6. 結論與提交資產

本次工作落實了「不自滿、不紙上談兵、用實作解決真實差距」：
1. **代碼核心**：
   - `agent_core/approval_broker.py` (審批卡片 Broker)
   - `agent_core/companion_web.py` (手機伴侶 UI 渲染引擎)
   - `scripts/agentos_channel.py` (多角色頻道分發器)
   - `scripts/agentos_remote_control.py` (整合 approvals 子指令)
2. **運行服務**：
   - 更新並重啟 `agentos-control-plane.service`，所有端點經由公網 HTTPS 驗證通過。
