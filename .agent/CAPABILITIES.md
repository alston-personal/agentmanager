# 🛡️ 石虎 AgentOS 功能註冊清冊 (CAPABILITIES.md)

## 🦁 核心定義 (Core Definition)
這是石虎 AgentOS 的 **「萬神殿」**。任何代碼開發前，必須先由此清冊檢索是否已有具備類似「意圖 (Intent)」的功能，嚴禁重複造輪子。

---

## 📋 註冊中功能 (Registry)

### 1. 維生與同步 (Life Support & Sync)
| 功能名稱 | 入口檔案 | 負責角色 | 狀態 | 說明 |
| :--- | :--- | :--- | :--- | :--- |
| **天啟訊號 (LCS-Signal)** | `bin/lcs-signal` | 虎掌/織圖 | 🔄 重造中 | 喚醒全體 Agent 服務，執行秩序重建與全域同步。 |
| **貓墨同步 (Cat-Ink)** | `scripts/core_services/session_syncer.py` | 虎掌/銳爪 | ✅ 現行 | 每 60 秒將對話備份至數據層。 |
| **蜂群狀態 (Swarm Status)** | `bin/status` | 鳴風/織圖 | ✅ 現行 | 視覺化監控 20+ 專案健康度。 |
| **核心狀態庫 (Agent Core)** | `agent_core/` | 虎掌/織圖 | ✅ 現行 | 提供設定載入、專案模型與 `project.yaml`/legacy `STATUS.md` 讀取。 |
| **知識內化器 (Internalizer)** | `scripts/internalize.py` | 織圖/書庫 | ✅ 現行 | 將記憶宮殿、Meditation、Ecosystem Report 與 Chronicle 蒸餾進 LLM Wiki。 |

### 2. 環境與發佈 (Env & Publish)
| 功能名稱 | 入口檔案 | 負責角色 | 狀態 | 說明 |
| :--- | :--- | :--- | :--- | :--- |
| **環境初始化 (Bootstrap)** | `scripts/bootstrap.py` | 虎掌 | ✅ 現行 | 自動修復數據橋接、Symbolic Links。 |
| **撰史遷移 (Migrate)** | `bin/migrate` | 織圖 | ✅ 現行 | 將全局進度同步至 `STATUS.md`。 |
| **石虎發佈器 (Publisher)** | `scripts/legacy/zeus_writer_...` | 鳴風/虎掌 | ✅ 現行 | Matters 與社交媒體自動發佈腳本。 |

---

## 🛠️ 開發與維運決策矩陣 (IDP)
1. **查詢現有能力**：先看本檔案與 `bin/` 目錄。
2. **優先複用**：若已有功能，不可重複撰寫。
3. **無則註冊**：若新增具備長期價值的功能，**必須** 更新本清冊。

---

## 🧩 AgentOS Capability Registry

AgentOS now treats reusable work as a capability, not a project-specific side effect.

### Registry Source of Truth
- `scripts/capability_registry.py`
- `agent_core/project_store.py`
- `agent-data/projects/*/project.yaml`

### Core Policy
- Projects may declare `capabilities_provided` and `capabilities_required`.
- The registry must be consulted before any cross-project orchestration.
- If a capability already exists in the registry, reuse or promote it instead of creating a parallel implementation.

### Registered Shared Capability
| Capability | Provider | Status | Notes |
| :--- | :--- | :--- | :--- |
| **Video Indexing Hub** | `video-indexing` | 🧠 Proposed | Central visual indexing, transcript grounding, and scene-map artifact producer for all video-aware projects. |

### Governance Capability
| Capability | Provider | Status | Notes |
| :--- | :--- | :--- | :--- |
| **Spec Stewardship** | `scripts/spec_steward.py` | ✅ 現行 | Scans specs, project declarations, and STATUS files to surface drift, stale specs, and missing ownership. |
| **AgentOS Status Center** | `scripts/agentos_status.py` | ✅ 現行 | Consolidated snapshot of roles, capabilities, projects, specs, and memory health for fast operational review. |
| **端口巡護者 (Port Manager)** | `scripts/core_services/port_manager.py` | ✅ 現行 | 負責自動分配與追蹤 22 個專案的連接埠配置，防止端口衝突 |

### Usage Pattern
```bash
python3 scripts/capability_registry.py
python3 scripts/capability_registry.py --provides video.index.visual
python3 scripts/capability_registry.py --requires video.index.visual
python3 scripts/spec_steward.py
python3 scripts/agentos_status.py
```

*「石虎 Agent 的能力不僅是寫出的代碼，更是已知的律法。」*
