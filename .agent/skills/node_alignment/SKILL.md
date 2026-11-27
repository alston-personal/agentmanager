---
name: node_alignment
description: 負責 AgentOS 全域跨節點身心校準（Node Alignment），檢測各 Node 與 Oracle ONE 中樞的心跳時效、版本一致性、能力邊界與殘留舊目錄，產出標準化校準報告。
---

# 🌐 AgentOS Node Alignment Skill (跨節點身心校準技能)

當系統發生重啟 (Crash/Restart)、版本更迭、網路重連或懷疑節點狀態不一致時，使用此技能對全域節點執行身心合一校準。

## 🎯 核心使命與校準三支柱 (Three Pillars)

1. **連線與心跳時效 (Transport & Heartbeat Freshness)**：
   - 驗證節點與 Central ONE (Port 8780 / Gateway 443) 雙向金鑰 Token 合法性。
   - 檢測節點心跳延遲（Freshness），即時裁定活躍度（`live` / `stale` / `offline`）。
2. **版本與代碼同步 (Code & Version Parity)**：
   - 比對各節點回報之版本、Git HEAD Commit 與 Central ONE 最新發行版。
   - 探測並提示清理邊緣節點遺留之歷史目錄（如 vopc5750 舊 `D:\agentos` legacy workflows）。
3. **能力邊界與執行表面 (Capability & Surface Alignment)**：
   - 驗證各節點回報之能力清單（Capabilities）與受治理白名單是否相符。
   - 實機探測節點表面（Windows GUI、Linux CLI/Docker、macOS）。

---

## 🛠️ 執行指令與校準程序

### 步驟 1：執行全域節點活性與校準稽核
在終端機執行：
```bash
python3 agent_core/node_alignment.py
```
或在 Python 中呼叫：
```python
from agent_core.node_alignment import NodeAlignmentEngine

engine = NodeAlignmentEngine()
report = engine.audit_all_nodes(max_stale_seconds=300)
```

### 步驟 2：派發特定節點表面探測 (Surface Alignment Probe)
若需強制更新特定節點（如 `vopc5750` 或 `dqa03restore`）的最新執行表面與能力：
```python
engine.dispatch_surface_alignment_probe("vopc5750")
```
節點 Thin Client 將在下次心跳週期消費任務，並回傳包含 IDE、CLI 與運行中 Agent 之不可否認 Receipt。

### 步驟 3：異狀排除與引導修復
- **若發現 `HEARTBEAT_STALE` 或 `NODE_OFFLINE`**：
  - Windows: 執行 `irm https://studio.milkcat.org/join | iex` 或點擊 `agentos-join.cmd` 重啟。
  - Linux/macOS: 執行 `curl -sSL https://studio.milkcat.org/join | bash`。
- **若發現歷史遺留目錄**：
  - Windows: 引導使用者封存或移除 `D:\agentos`，徹底落實純 Thin Client 架構。
