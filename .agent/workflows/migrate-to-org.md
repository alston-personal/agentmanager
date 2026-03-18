---
description: 一鍵搬移 (One-Click Migration) - 初始化環境並同步所有專案到 Organization
---

# /migrate-to-org - 一鍵遷移至 Organization

此指令用於將目前的本地專案批次遷移到 GitHub Organization (`alston-personal`) 並同步環境。

## 執行步驟

### 1. 認證檢查
檢查 `.gh_token` 是否存在且有效。
```bash
export GITHUB_TOKEN=$(cat /home/ubuntu/agentmanager/.gh_token)
gh auth status
```

### 2. 批量遷移 (Migrate)
將指定的本地專案推送到 Organization：
```python
from workspace_manager_client import WorkspaceManager
manager = WorkspaceManager("/home/ubuntu/agentmanager")

# 範例：搬移 y2help-web
print(manager.migrate_project_to_org("y2help-web"))
```

### 3. 同步工作區 (Relink)
確保 `/home/ubuntu/` 下的所有實體目錄都在 `workspace/` 有對應捷徑：
```bash
python /home/ubuntu/agentmanager/.agent/skills/workspace_manager/workspace_manager_client.py relink
```

### 4. 更新 Dashboard
讀取 Org 列表並更新 `DASHBOARD.md` 狀態。

## ⚠️ 注意事項
- 執行前請確認本地 Git 已經 `commit` 完成。
- 遷移會修改專案的 `remote origin`。
- 私人密鑰 (.env) 不會被推送到 GitHub，需手動或使用 `secret_manager` 處理。
