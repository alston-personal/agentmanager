---
description: 一鍵搬移 (One-Click Migration) - 初始化環境並同步所有專案
---

# /migrate - 一鍵搬移與環境初始化

此指令用於將目前的環境初始化為 AIGP (AI Global Project) Workspace，並從 Command Center 同步所有專案。

## 執行步驟

### 1. 環境診斷
檢查 `git`, `python`, `pip` 是否已安裝。

### 2. 設定 Git 身分 (重要！)
**為了避免 git commit 失敗，必須先設定身分：**
```bash
git config --global user.email "alston.huang@vivotek.com"
git config --global user.name "Alston"
```

### 3. 加入 Token 與憑證
檢查或建立以下檔案：
- `.gh_token`: 儲存 GitHub Personal Access Token
- `.env`: 儲存環境變數
- `config.json`: 儲存專案配置 (repo 名稱等)

### 4. 初始化目錄結構與 Skills
```bash
mkdir -p .agent/workflows memory projects
# 克隆共享 Skills
git clone https://$(cat .gh_token)@github.com/alstonhuang/shared-agent-skills.git .agent/skills
```

### 5. 同步所有專案 (一鍵搬移核心)
使用 `WorkspaceManager` 批量同步專案：
```python
from workspace_manager_client import WorkspaceManager
manager = WorkspaceManager(".")
manager.sync_all_projects()
```

### 6. 完成回報
向用戶確認進度：
> "✅ 搬家完成！
> 1. Git 身分已設定。
> 2. Skills 已同步。
> 3. 所有專案已從 Command Center 拉取完成。"

## ⚠️ 注意事項
- 確保 `.gh_token` 權限正確。
- 如果專案資料夾已存在，將會跳過克隆。
- 此 workflow 應在全新的目錄中優先執行。
