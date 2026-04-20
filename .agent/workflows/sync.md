---
description: Synchronize both logic and data layers (Git Pull)
---
// turbo-all

# /sync - 對齊 AgentOS 全域意識

## 📍 目的
當你在多台設備間切換（例如從本地筆電換到雲端開發環境），或者感覺「記憶不同步」時執行。此指令會強制拉取遠端最新代碼與資料狀態。

## ⚙️ 核心流程 (Steps)

1. **執行同步腳本**
   ```bash
   /bin/bash /home/ubuntu/agentmanager/scripts/sync_brain.sh
   ```

2. **確認狀態 (Status Check)**
   同步完成後，建議執行 `/status` 查看看板是否已更新到最新時間戳。

3. **重新加掛服務 (Only if needed)**
   如果你是在 Core 機器上發現同步後代碼發生大變動，建議執行 `/reboot` (重啟服務)。

---
> [!TIP]
> 如果發生 Git Conflict (衝突)，請手動進入專案目錄解決衝突後再重新執行 `/sync`。
