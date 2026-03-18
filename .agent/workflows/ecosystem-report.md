---
description: Create a dated snapshot summary of the entire Agent OS ecosystem
---
// turbo-all

# /ecosystem-report - 全系統狀態總結報告

這個工作流會掃描所有在 `agent-data` 註冊的專案，產生一個全方位的健康檢查報告。

## Steps

1. **環境健康檢查 (System Health)**
   ```bash
   echo "--- SERVER HEALTH ---"
   uptime
   free -h
   df -h / | tail -n 1
   echo "---------------------"
   ```

2. **服務狀態檢查 (Services)**
   ```bash
   echo "--- ACTIVE SERVICES ---"
   systemctl --user status tg-commander.service | grep -E "Active|Main PID"
   # 可以增加 n8n 或其他服務的檢查
   echo "---------------------"
   ```

3. **專案進度矩陣 (Project Matrix)**
   掃描並格式化所有專案的最新狀態：
   ```bash
   echo "| Project | Status | Last Update | Latest Activity |"
   echo "| :--- | :--- | :--- | :--- |"
   for s_path in /home/ubuntu/agent-data/projects/*/STATUS.md; do
       p_name=$(basename $(dirname "$s_path"))
       last_status=$(grep "| **Last Status** |" "$s_path" | cut -d'|' -f3 | sed 's/^[[:space:]]*//;s/[[:space:]]*$//')
       last_updated=$(grep "| **Last Updated** |" "$s_path" | cut -d'|' -f3 | sed 's/^[[:space:]]*//;s/[[:space:]]*$//')
       latest_log=$(grep "^-" "$s_path" | head -n 1 | sed 's/^- //')
       echo "| **$p_name** | $last_status | $last_updated | $latest_log |"
   done
   ```

4. **產生 Snapshot 存檔**
   將報告內容同時寫入 `/home/ubuntu/agent-data/journals/ecosystem_reports/report_$(date +%Y%m%d).md`。

5. **回報給用戶**
   將上述表格與系統狀況呈報給用戶。
