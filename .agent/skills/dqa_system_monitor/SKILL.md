---
name: dqa_system_monitor
description: 專門用於檢測與回報 DQA 核心服務 (Redmine/TestRail/Samba) 運作狀態、NAS 掛載及備份狀況的即時監控工具。
---

# DQA System Monitor Skill

## 🎯 目的
快速檢測並產生 DQA 系統服務（Redmine、TestRail、Samba、Gateway、NAS 掛載、每日備份及 Watchdog）的即時運作狀態報告，避免手動輸入繁瑣的 Docker 或系統指令。

## 📋 使用方法
在終端機中執行 Python 腳本，它會自動彙整所有系統指標並輸出格式化後的 Markdown 報告：

```bash
python3 /home/dqa03/agentos/.agent/skills/dqa_system_monitor/scripts/check_services.py
```

## 🔍 檢測指標包含
1. **Watchdog Heartbeat**：確認自癒監控是否正常運作與最後心跳時間。
2. **Docker Containers**：檢測 Redmine、TestRail、Samba、Search 與 Gateway 的容器狀態。
3. **NAS Mounts**：驗證 `/mnt/QMD` 與 `/mnt/NasBackup` 是否成功掛載且空間充足。
4. **Daily Backup Logs**：檢查 `/home/dqa03/system/logs/daily_backup.log` 的最後執行結果。
