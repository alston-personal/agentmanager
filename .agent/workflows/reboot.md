---
description: Gracefully reboot AgentOS services and re-link bridges
---
// turbo-all

# /reboot - 重啟 AgentOS 系統服務

## 📍 目的
當修改了 `.env`、更新了 `systemd` unit 文件、或者執行了 `/sync` 導致代碼大變動後，使用此指令強制重置軟連結與服務狀態。

## ⚙️ 核心流程 (Steps)

1. **執行重啟腳本**
   ```bash
   /bin/bash /home/ubuntu/agentmanager/scripts/reboot_os.sh
   ```

2. **驗證健康度**
   重啟完成後，會自動執行 `recall_chronicle.py` 以找回最新的系統編年史記憶。

---
> [!IMPORTANT]
> 此指令僅在 `AGENT_MODE=CORE` 的機器上會實際重啟 Telegram Bot 等服務。在 Client 機器上，它僅會執行重新建立軟連結 (Relink) 的動作。
