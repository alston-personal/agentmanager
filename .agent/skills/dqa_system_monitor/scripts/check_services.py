#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import subprocess
import os
import sys

def run_cmd(cmd, shell=False):
    try:
        res = subprocess.run(cmd, shell=shell, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=10)
        return res.stdout.strip(), res.returncode
    except Exception as e:
        return f"Error: {str(e)}", -1

def get_docker_status():
    # 透過 sudo 安全取得容器狀態
    cmd = "echo 'dqa03' | sudo -S docker ps -a --format '{{.Names}}|{{.Image}}|{{.Status}}'"
    out, code = run_cmd(cmd, shell=True)
    if code != 0:
        return f"❌ 無法取得 Docker 狀態: {out}", False
    
    lines = out.split('\n')
    containers = {}
    for line in lines:
        if not line.strip() or "sudo" in line:
            continue
        parts = line.split('|')
        if len(parts) == 3:
            name, img, status = parts
            containers[name] = {"image": img, "status": status}
    return containers, True

def get_watchdog_status():
    status_file = "/home/dqa03/system/logs/watchdog.status"
    if os.path.exists(status_file):
        try:
            with open(status_file, 'r', encoding='utf-8') as f:
                return f.read().strip()
        except Exception as e:
            return f"❌ 讀取看門狗狀態失敗: {str(e)}"
    return "❌ 找不到 watchdog.status 檔案"

def get_backup_status():
    log_file = "/home/dqa03/system/logs/daily_backup.log"
    if os.path.exists(log_file):
        try:
            with open(log_file, 'r', encoding='utf-8') as f:
                lines = f.readlines()
                # 取得最後 15 行非空行
                last_lines = [l.strip() for l in lines[-15:] if l.strip()]
                return "\n".join(last_lines)
        except Exception as e:
            return f"❌ 讀取備份日誌失敗: {str(e)}"
    return "❌ 找不到 daily_backup.log 檔案"

def get_mount_status():
    out, code = run_cmd(["df", "-h", "/mnt/QMD", "/mnt/NasBackup"])
    if code != 0:
        return f"❌ 掛載點檢查失敗: {out}"
    return out

def main():
    print("# 📊 DQA 系統服務狀態即時回報\n")
    
    # 1. Watchdog 心跳
    print("## ⏱️ Watchdog 自癒監控")
    wd = get_watchdog_status()
    if "Healthy" in wd:
        print(f"**目前狀態**：🟢 `{wd}`\n")
    else:
        print(f"**目前狀態**：🔴 `{wd}`\n")
        
    # 2. 容器狀態
    print("## 🐳 Docker 容器狀態")
    containers, ok = get_docker_status()
    if not ok:
        print(containers)
    else:
        expected = {
            "Redmine": ["system-gateway", "system-redmine_app", "system-redmine_db", "system-redmine_search"],
            "TestRail": ["system-gateway", "system-testrail_app", "system-testrail_scheduler", "system-testrail_db"],
            "Samba": ["system-samba"]
        }
        tm_containers = ["redmine_time_machine_app", "redmine_time_machine_db", "testrail_time_machine_app", "testrail_time_machine_db"]
        
        print("| 服務群組 | 容器名稱 | 映像檔 (Image) | 運作狀態 (Status) | 燈號 |")
        print("| :--- | :--- | :--- | :--- | :---: |")
        
        for group, names in expected.items():
            for name in names:
                if name in containers:
                    status = containers[name]["status"]
                    img = containers[name]["image"]
                    indicator = "🟢" if "Up" in status else "🔴"
                    print(f"| {group} | `{name}` | `{img}` | {status} | {indicator} |")
                else:
                    print(f"| {group} | `{name}` | - | 未建立/不存在 | ❌ |")
        
        # 檢查時光機
        tm_running = [name for name in tm_containers if name in containers and "Up" in containers[name]["status"]]
        if tm_running:
            print("\n⚠️ **偵測到正在運作的時光機測試環境 (Sandbox)：**")
            for name in tm_running:
                print(f"- `{name}`: {containers[name]['status']} 🟡")
        else:
            print("\n💡 *時光機測試環境 (`-tm`) 目前皆為關閉/靜止狀態（正常現象）。*")
            
    # 3. 掛載狀態
    print("\n## 💾 儲存與 NAS 掛載點")
    print("```")
    print(get_mount_status())
    print("```")
    
    # 4. 備份狀態
    print("\n## 🔄 每日備份執行日誌 (最後狀態)")
    backup = get_backup_status()
    print("```")
    print(backup)
    print("```")

if __name__ == "__main__":
    main()
