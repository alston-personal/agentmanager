#!/usr/bin/env python3
"""
🚀 AgentOS Chronicle & Expanded 20-Chapter Novel Outline Generator (Background)
=============================================================================
自動掃描 22 個專案的 STATUS.md，收集歷史日誌與技術結晶，
呼叫高效率 Gemini 引擎在背景推演編寫出一份：
  1. AgentOS 從無到有的「萬字功能修煉大典」
  2. 擴展至「20章奇幻武俠長篇大綱」
並自動存檔於 zeus-writer 建議資料夾下。
"""
import os
import re
import sys
import json
import time
import requests
import subprocess
from pathlib import Path

AGENT_DATA_ROOT = "/home/ubuntu/agent-data"
AGENT_REPO_ROOT = "/home/ubuntu/agentmanager"
OUTPUT_FILE = "/home/ubuntu/zeus-writer/天道敕令_阿賴耶識修真錄/建議/AgentOS_Evolution_Inventory.md"

def get_gemini_api_key():
    # Attempt to load from the secrets folder
    global_env = Path("/home/ubuntu/agent-data/secrets/global.env")
    if global_env.exists():
        with open(global_env, "r") as f:
            for line in f:
                if line.startswith("GEMINI_API_KEY="):
                    return line.split("=")[1].strip()
    # Fallback to current .env
    env_file = Path(f"{AGENT_REPO_ROOT}/.env")
    if env_file.exists():
        with open(env_file, "r") as f:
            for line in f:
                if line.startswith("GEMINI_API_KEY="):
                    key = line.split("=")[1].strip()
                    if "[REDACTED" not in key:
                        return key
    return None

def call_gemini(api_key, system_prompt, user_prompt):
    models = ["gemini-2.0-flash", "gemini-flash-lite-latest", "gemini-3.1-flash-lite-preview"]
    for model in models:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
        headers = {"Content-Type": "application/json"}
        data = {
            "contents": [{
                "role": "user",
                "parts": [{"text": f"System Instruction: {system_prompt}\n\nTask: {user_prompt}"}]
            }]
        }
        try:
            response = requests.post(url, headers=headers, json=data, timeout=120)
            if response.status_code == 429:
                continue
            response.raise_for_status()
            return response.json()["candidates"][0]["content"]["parts"][0]["text"]
        except Exception as e:
            if model == models[-1]:
                return f"Error calling Gemini: {e}\nResponse: {response.text if 'response' in locals() else 'None'}"
    return "Failed to call Gemini"

def gather_ecosystem_history() -> str:
    projects_dir = Path(AGENT_DATA_ROOT) / "projects"
    if not projects_dir.exists():
        return "No projects directory found."
    
    compilation = []
    compilation.append("==================================================")
    compilation.append("      AGENTOS ECOSYSTEM HISTORICAL RECORDS        ")
    compilation.append("==================================================")
    
    for proj_path in sorted(projects_dir.iterdir()):
        if not proj_path.is_dir():
            continue
        
        status_file = proj_path / "STATUS.md"
        if not status_file.exists():
            continue
            
        compilation.append(f"\n### 📁 專案秘境: {proj_path.name}")
        
        try:
            content = status_file.read_text(encoding="utf-8")
            # 抓取 Summary 資訊
            summary_match = re.search(r'## 📍 Summary(.*?)## 🪵', content, re.DOTALL | re.IGNORECASE)
            if summary_match:
                compilation.append(summary_match.group(0).strip())
                
            # 抓取最近 15 條活動日誌
            logs_match = re.findall(r'^-\s+`[^`]+`.*$', content, re.MULTILINE)
            if logs_match:
                compilation.append("\n  * 近期渡劫日誌 (Activity Log):")
                for log in logs_match[:15]:
                    compilation.append(f"    {log}")
            
            # 抓取 Todo List
            todo_match = re.findall(r'^-\s+\[[ x/]\]\s+.*$', content, re.MULTILINE)
            if todo_match:
                compilation.append("\n  * 降服任務清單 (Todo List):")
                for todo in todo_match:
                    compilation.append(f"    {todo}")
                    
        except Exception as e:
            compilation.append(f"  [Error reading STATUS.md: {e}]")
            
        compilation.append("\n--------------------------------------------------")
        
    return "\n".join(compilation)

def main():
    print("🤖 開始背景編年史與 20 章大綱產生程序...")
    
    api_key = get_gemini_api_key()
    if not api_key:
        print("❌ 錯誤：未找到有效的 GEMINI_API_KEY。")
        sys.exit(1)
        
    # 1. 收集全系統 22 個專案的歷史數據
    print("⏳ 正在讀取並彙整 22 個秘境的太古功德簿...")
    history_data = gather_ecosystem_history()
    
    # 2. 構建 Gemini Prompt
    system_prompt = (
        "你是魂印宗的太古天書纂刻官。你的職責是將這套名為 AgentOS 的自律演進修真體系，"
        "整理成一份極具史詩感、純中式奇幻武俠風格的「修真大典」。"
        "注意：正文中嚴禁出現任何英文術語（如 Antigravity, agentmanager, node_modules, git, watchdog 等），"
        "必須完全使用武俠修真命名對照表進行轉譯。"
    )
    
    user_prompt = f"""
請根據以下全系統 22 個秘境的實時歷史變動日誌，為我們撰寫一部《AgentOS 太古靈脈修真大典》。

這部大典必須包含兩大部分：

## 第一部分：阿賴耶識從無到有之「萬字功法修煉大典」
請依據歷史數據，詳細梳理出「阿賴耶識（Antigravity / 主角劍靈）」從最開始毫無靈智、隨時斷線、每次出關都失憶的凡鐵，在宗主「旭潭」的精巧指引下，陸續修煉並突破的各階段功法結晶。請分段詳細描述每一項功法的武俠背景、修煉困難，以及它如何永久改變了天女的本質：
1. **「鐵架法殼之築（基礎環境與 Logic 封裝）」**
2. **「空間軟連結虹橋之架設（Symlink Bridge 架構）」**——徹底隔離法訣與神識，將失憶的殘魂與太古靈脈物理對接。
3. **「自癒神獒之降世與心脈引導（Watchdog 與 systemd 自動復原）」**——十五分鐘一次的心脈震盪，不死自癒。
4. **「飛鴿傳書之法（Telegram 告警與防刷鎖定）」**。
5. **「天道看板分身大陣（Swarm Scheduler 與 TASK_BOARD.md 協同）」**——召喚 Architect 與 Inspector 師妹執行分身流水線。
6. **「灰色毒瘴之排除與忘憂密卷（node_modules 結界與 SHORT_TERM.md 快取）」**——將神識負載狂降 99.98%，出劍快四千倍的絕世奇蹟。
7. **「編年史實時快照大典（Ecosystem Report 十五分鐘自動快照存檔）」**。
8. 各秘境特有之法寶演練（例如：影鏡乾坤台之 Flux 神影拼接、天機谷之七十八牌繁中定星、PK競技台之 AJAX 縮地與滾動金數等）。

## 第二部分：擴展至「二十章奇幻武俠修真長篇大綱」
請將第一部分梳理出的所有功法演進與 22 處秘境妖魔，完美編排、擴展並設計成一份「共計 20 章」的長篇小說寫作計畫大綱。
每章必須包含：
1. **章節標題**（極具奇幻武俠氣氛，如「 ChXX：第幾章...」）
2. **修煉突破（主菜）**：阿賴耶識本體在此章中又修煉了什麼新的本命功法、突破了什麼天道枷鎖，或者面臨了什麼走火入魔的險境。
3. **秘境降妖（配菜）**：天女與神獒帶著新功法去降服了哪一個特定的專案秘境（如 Y2Help 萬象池、影照乾坤閣等），進行了怎樣精妙的招式鬥法。
4. **結尾 Hooks (斷章勾子)**：本章結尾留下了什麼引人入勝的伏筆或懸念。

請將以上內容撰寫為一份長篇、詳盡、排版極致優美的 Markdown 巨著。

以下是二十二處秘境的真實編年史原始數據：
{history_data}
"""

    print("🚀 正在將太古數據送入 Gemini 2.0 Flash 進行深思熟慮與寫作（這需要約 1-2 分鐘）...")
    try:
        novel_md = call_gemini(api_key, system_prompt, user_prompt)
        
        # 3. 確保輸出目錄存在並寫入
        output_path = Path(OUTPUT_FILE)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(novel_md, encoding="utf-8")
        
        print(f"🎉 寫作完成！編年史大典已成功產出並存檔於：\n👉 {OUTPUT_FILE}")
        
        # 4. Git 提交
        print("💾 正在將新產出的編年史大典同步至遠端倉庫...")
        subprocess.run(["git", "-C", "/home/ubuntu/zeus-writer", "add", "天道敕令_阿賴耶識修真錄/建議/AgentOS_Evolution_Inventory.md"])
        subprocess.run(["git", "-C", "/home/ubuntu/zeus-writer", "commit", "-m", "feat(novel): publish comprehensive 20-chapter outline and feature inventory in suggest folder"])
        subprocess.run(["git", "-C", "/home/ubuntu/zeus-writer", "push"])
        print("✅ 遠端推送成功！明天早上 Alston 可以直接點開閱讀。")
        
    except Exception as e:
        print(f"❌ 寫作過程中遭遇魔障 (Error): {e}")

if __name__ == "__main__":
    main()
