---
name: workspace_manager
description: 管理跨 workspace 的配置、同步和註冊功能
---

# Workspace Manager Skill

## 🎯 目的

管理多個物理 workspace 的配置、同步和與虛擬根（AI Command Center）的連接。

---

## 🚀 功能

### 1. **自動註冊 Workspace**
將當前 workspace 註冊到 AI Command Center，包括：
- Workspace 名稱和位置
- 機器資訊（主機名、作業系統）
- 包含的專案列表

### 2. **同步 Skills 和 Workflows**
從 GitHub 同步最新的 skills 和 workflows：
```python
manager.sync_skills()      # 從 shared-agent-skills 拉取最新版本
manager.sync_workflows()   # 從 agent-global-config 拉取 workflows
```

### 3. **Workspace 資訊查詢**
查詢並報告當前 workspace 的狀態：
```python
info = manager.get_workspace_info()
# 返回：workspace 名稱、路徑、包含的專案、Skills 版本等
```

### 4. **跨 Workspace 專案搜尋**
在 AI Command Center 中搜尋專案，找出它所在的 workspace：
```python
location = manager.find_project("AssetMaster")
# 返回：專案所在的 workspace 和路徑
```

---

## 📋 使用方法

### 初始設定（一次性）

```python
# 安裝依賴
!pip install PyGithub requests

# 載入 workspace manager
from workspace_manager_client import WorkspaceManager

# 初始化（需要 GitHub token）
TOKEN = "your_github_token"
manager = WorkspaceManager(TOKEN)

# 註冊當前 workspace
manager.register_workspace(
    name="AgentManager",
    location="d:\\AgentManager",
    description="主控 workspace，包含 AssetMaster 和 if-tv-station 專案"
)
```

### 日常使用

```python
# 同步 skills（拉取最新版本）
manager.sync_skills()

# 查看當前 workspace 資訊
info = manager.get_workspace_info()
print(f"Workspace: {info['name']}")
print(f"包含專案: {', '.join(info['projects'])}")

# 搜尋專案位置
location = manager.find_project("AssetMaster")
print(f"AssetMaster 在: {location}")

# 列出所有已註冊的 workspaces
workspaces = manager.list_all_workspaces()
for ws in workspaces:
    print(f"- {ws['name']} ({ws['location']})")
```

---

## 🔧 命令列模式

也可以直接從命令列使用：

```powershell
# 註冊當前 workspace
python workspace_manager_client.py register --name "MyWorkspace" --location "C:\MyWorkspace"

# 同步 skills
python workspace_manager_client.py sync-skills

# 查看 workspace 資訊
python workspace_manager_client.py info

# 列出所有 workspaces
python workspace_manager_client.py list
```

---

## 📁 資料儲存位置

Workspace 的註冊資訊儲存在 AI Command Center：

```
AI_Command_Center/
└─ workspaces/
   ├─ config.json           # 所有 workspace 列表
   └─ [workspace-name]/
      ├─ info.json          # Workspace 詳細資訊
      └─ projects.json      # 此 workspace 包含的專案
```

---

## 🔄 自動化 Workflow

### `/init-workspace` - 初始化新 Workspace

當你在新的環境開啟新 workspace 時：

```
1. 檢測是否已是 Git 倉庫
2. 創建 .agent/ 目錄結構
3. 克隆 shared-agent-skills 到 .agent/skills/
4. 克隆 workflows 到 .agent/workflows/
5. 創建 memory/ 和 projects/ 目錄
6. 設定語言偏好（繁體中文）
7. 註冊到 AI Command Center
8. 生成 workspace 配置檔案
```

### `/sync` - 同步 Skills 和 Workflows

```
1. 拉取 shared-agent-skills 最新版本
2. 拉取 workflows 最新版本
3. 更新本地配置
4. 回報同步狀態到 Command Center
```

---

## ⚠️ 注意事項

### 1. **GitHub Token 安全**
- 不要將 token 硬編碼在腳本中
- 使用 `.env` 或 `.gh_token` 檔案儲存
- 確保這些檔案在 `.gitignore` 中

### 2. **Workspace 命名**
- 使用有意義的名稱（如 "AgentManager", "RemoteVM1"）
- 避免使用相同名稱註冊多個 workspace
- 名稱應該是唯一的

### 3. **同步頻率**
- 不需要每次都同步 skills
- 建議：每週或有更新時才同步
- 避免頻繁的 Git 操作

### 4. **權限管理**
- 確保所有倉庫（AI_Command_Center, shared-agent-skills）都是私有的
- 只分享 token 給信任的環境
- 定期更新 token

---

## 🧪 測試

```python
# 測試連接
manager.test_connection()  # 應返回 True

# 測試 GitHub API
manager.test_github_access()  # 檢查是否能訪問倉庫

# 驗證 workspace 註冊
manager.verify_registration()  # 確認已正確註冊
```

---

## 📚 API 參考

### WorkspaceManager 類別

```python
class WorkspaceManager:
    def __init__(self, github_token: str, command_center_repo: str = "alstonhuang/AI_Command_Center")
    
    def register_workspace(self, name: str, location: str, description: str = "") -> bool
    def sync_skills(self, target_path: str = ".agent/skills") -> bool
    def sync_workflows(self, target_path: str = ".agent/workflows") -> bool
    def get_workspace_info(self) -> dict
    def find_project(self, project_name: str) -> dict
    def list_all_workspaces(self) -> list
    def test_connection(self) -> bool
```

---

## 🔗 相關資源

- [虛擬根架構設計](../VIRTUAL_ROOT_ARCHITECTURE.md)
- [新 Workspace 設定指南](../NEW_WORKSPACE_SETUP.md)
- [Command Center Reporter Skill](../command_center_reporter/SKILL.md)
- [AI Command Center 倉庫](https://github.com/alstonhuang/AI_Command_Center)

---

## 🆘 疑難排解

### 問題 1：無法連接到 GitHub
```python
# 檢查 token 是否有效
manager.test_github_access()

# 檢查網路連接
import requests
requests.get("https://api.github.com").status_code  # 應該是 200
```

### 問題 2：Skills 同步失敗
```powershell
# 手動檢查
cd .agent/skills
git status
git pull

# 如果有衝突，重置
git reset --hard origin/main
```

### 問題 3：Workspace 未註冊
```python
# 重新註冊
manager.register_workspace("WorkspaceName", "C:\\Path\\To\\Workspace")

# 驗證
manager.verify_registration()
```

---

**透過 Workspace Manager，你可以輕鬆管理多個 workspace，實現真正的跨環境協作！**
