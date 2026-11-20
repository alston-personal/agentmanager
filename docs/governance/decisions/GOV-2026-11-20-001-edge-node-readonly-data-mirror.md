# GOV-2026-11-20-001: 邊緣節點唯讀資料鏡像與單一遠端寫入律 (Edge Node Read-Only Data Mirror)

- **Decision ID**: `GOV-2026-11-20-001`
- **Status**: `ACCEPTED` (Human Sovereign Mandate)
- **Date**: `2026-11-20`
- **Constitution Principle**: `edge_node_readonly_data_mirror` (`level: immutable`)
- **Owners**: `governance.keeper`, `system.cartographer`, `agentos_node`

## 1. 背景與問題 (Context)

`agent-data` 是整個 AgentOS 生態的高頻動態真相層（包含 PDCA 心跳事件、角色日誌、Canonical IR、Realm 狀態與規格索引），由 Oracle Cloud Core 持續寫入。

過去若在邊緣節點（如 Windows 工作站 `vopc5750`）直接 Clone `agent-data` 並進行雙向讀寫（本地 commit + push），必然導致：
1. 本地快速落後雲端數千筆高頻提交；
2. 邊緣節點 push 後，雲端真相層因工作區存在即時寫入檔案而無法 fast-forward/rebase，引發嚴重的雙向分叉與同步卡死。

相對地，若邊緣節點完全不保留任何本地資料，純靠 MCP 逐檔讀寫，則會喪失本地 IDE 極速搜尋、離線查閱與批次 Linter 掃描能力。

## 2. 憲法裁定 (Decision — CQRS 讀寫分離架構)

所有 AgentOS 邊緣節點（Node）必須嚴格遵循 **「本地唯讀鏡像（Read-Only Mirror）＋ 遠端單一寫入（Remote Write）」** 原則：

1. **唯讀本地鏡像 (Read Replica)**：
   - 邊緣節點可維護一份 `agent-data` 的本地鏡像供極速讀取、全文檢索與批次靜態檢查。
   - 該本地鏡像必須物理鎖死禁止推送：
     ```bash
     git remote set-url --push origin DISABLED_READ_ONLY_MIRROR
     ```
2. **定期單向強制同步 (One-Way Sync)**：
   - 邊緣節點透過 `agentos_node/data_mirror.py` 定期執行 `git fetch origin && git reset --hard origin/main`，確保本地永遠為雲端唯一真相源的乾淨鏡像，絕不產生 dirty working tree 或本地分叉。
3. **遠端單一寫入 (Remote Write Only)**：
   - 邊緣節點嚴禁在本地 `agent-data` 進行 commit 或 push。
   - 所有狀態更新、規格變更與記憶寫入，一律透過 `agentos-one` MCP、Control Plane API 或 Remote-SSH 直接寫回雲端唯一真相源（Oracle Core）。

## 3. 實體執法與驗證 (Enforcement & Migration)

- **執法模組**：[`agentos_node/data_mirror.py`](file:///home/ubuntu/agentmanager/agentos_node/data_mirror.py) 提供標準化之 `ensure_readonly_push_lock()`、`verify_readonly_mirror()` 與 `sync_readonly_mirror()`。
- **單元測試**：[`tests/test_edge_data_mirror.py`](file:///home/ubuntu/agentmanager/tests/test_edge_data_mirror.py) 驗證推播物理鎖死、違法 push URL 攔截與單向同步行為。
- **既有節點遷移**：凡既有邊緣節點（如 `vopc5750`）仍持有可寫入之 `agent-data` Clone，應立即執行 `ensure_readonly_push_lock()` 鎖死 push URL 並切換為單向定時拉取模式。
