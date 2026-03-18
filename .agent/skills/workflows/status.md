---
description: Show current status of all AI projects in the Command Center
---

# /status - 查看 AI 指揮中心全系統狀態

## 重要：資料來源
所有狀態數據必須從 **中央資料庫** (`/home/ubuntu/agent-data/projects/`) 讀取。
**不是** 從 `agentmanager/projects/` 讀取。

## Steps

1. **掃描中央資料庫**
   ```bash
   for s_path in /home/ubuntu/agent-data/projects/*/STATUS.md; do
       p_name=$(basename $(dirname "$s_path"))
       last_status=$(grep "| **Last Status** |" "$s_path" | cut -d'|' -f3 | sed 's/^[[:space:]]*//;s/[[:space:]]*$//')
       last_updated=$(grep "| **Last Updated** |" "$s_path" | cut -d'|' -f3 | sed 's/^[[:space:]]*//;s/[[:space:]]*$//')
       latest_log=$(grep "^-" "$s_path" | head -n 1)
       echo "[$p_name] | $last_status | $last_updated | $latest_log"
   done
   ```

2. **呈現為格式化表格**
   以 Markdown 表格格式向用戶呈現：
   - 專案名稱
   - 目前狀態 (Last Status)
   - 最後更新時間
   - 最近活動摘要

3. **額外檢查 (選項)**
   - 如果用戶想知道哪些服務正在運行：`sudo docker ps` 與 `ps aux | grep node`
   - 如果用戶想知道軟連結是否正常：檢查各專案的 `STATUS.md` 是否為 symlink
