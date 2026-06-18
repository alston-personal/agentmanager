# 📊 Daily Health & Status Report
**Generated:** 2026-06-17 09:00:01

## 1. AgentOS Repository Status
```text
On branch main
Your branch is up to date with 'origin/main'.

Changes not staged for commit:
  (use "git add <file>..." to update what will be committed)
  (use "git restore <file>..." to discard changes in working directory)
	modified:   .vscode/settings.json
	modified:   litellm/config.yml
	modified:   litellm/run.sh

Untracked files:
  (use "git add <file>..." to include in what will be committed)
	reports/daily_reports/2026-06-09_health_report.md
	reports/daily_reports/2026-06-10_health_report.md
	reports/daily_reports/2026-06-11_health_report.md
	reports/daily_reports/2026-06-12_health_report.md
	reports/daily_reports/2026-06-13_health_report.md
	reports/daily_reports/2026-06-14_health_report.md
	reports/daily_reports/2026-06-15_health_report.md
	reports/daily_reports/2026-06-16_health_report.md

no changes added to commit (use "git add" and/or "git commit -a")
```

## 2. Docker Containers Health
```text
NAMES                       STATUS                    PORTS
system-samba                Up 21 hours (unhealthy)   
system-testrail_scheduler   Up 4 days                 9000/tcp
system-testrail_app         Up 4 days                 9000/tcp
system-testrail_db          Up 4 days                 3306/tcp, 33060/tcp
system-redmine_app          Up 6 days                 
system-redmine_db           Up 6 days                 3306/tcp, 33060/tcp
system-gateway              Up 6 days                 0.0.0.0:80->80/tcp, [::]:80->80/tcp, 0.0.0.0:443->443/tcp, [::]:443->443/tcp
testrail_time_machine_db    Exited (0) 5 weeks ago    
redmine_time_machine_db     Exited (1) 7 weeks ago    
testrail_time_machine_app   Exited (0) 7 weeks ago    
system-redmine_search       Up 6 days                 0.0.0.0:9200->9200/tcp, [::]:9200->9200/tcp
```

## 3. System Disk Usage
```text
Filesystem                         Size  Used Avail Use% Mounted on
/dev/mapper/ubuntu--vg-ubuntu--lv  2.0T  884G  1.1T  46% /
//172.19.16.88/QMD                  42T   29T   14T  69% /mnt/QMD
```

## 4. Pending TODOs in STATUS.md (Top 5)
```text
- [ ] Automate daily ecosystem reports via Gemini.
- [ ] Integrate Skill Promotion (LCS-Synthesis) into UI.
- [ ] **[LCS-Optimization]** 實裝 `STATUS.md` 滾動歸檔與全域 `pulse.json` 高速快取 (Phase 1)
- [ ] **[Security Hardening]** 導入 `detect-secrets` 預檢防漏，將憑證移入加密儲存區 (Phase 2)
- [ ] **[Watchdog Evolution]** 重寫自癒神獒（事件驅動版），實裝非同步調度退避機制 (Phase 3)
```

---
*End of automated daily report.*
