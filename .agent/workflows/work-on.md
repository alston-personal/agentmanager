---
description: 快速切換並進入特定專案工作模式
---
// turbo-all

## 🚦 `/work-on [專案名稱]` 工作流

當用戶輸入 `/work-on <project-name>` 時，執行以下步驟：

### Step 1: 確認專案存在
```bash
ls -ld /home/ubuntu/<project-name>/
```
- 如果不存在，列出 `/home/ubuntu/agent-data/projects/` 下所有可用專案名稱供用戶選擇。

### Step 2: 讀取核心規範
讀取 `/home/ubuntu/agentmanager/.agent/rules/LOGIC_DATA_SEPARATION.md`，確保理解邏輯/資料分離架構：
- **代碼 (Code)**：存放在 `/home/ubuntu/<project-name>/`
- **狀態 (Data)**：存放在 `/home/ubuntu/agent-data/projects/<project-name>/`
- **STATUS.md** 和 **memory/** 是軟連結，指向 agent-data，**嚴禁覆寫或刪除軟連結**

### Step 3: 讀取專案狀態
```bash
cat /home/ubuntu/agent-data/projects/<project-name>/STATUS.md
```

### Step 4: 讀取專案記憶 (如果存在)
```bash
ls /home/ubuntu/agent-data/projects/<project-name>/memory/
# 讀取 short_term.md 和 long_term.md (如果存在)
cat /home/ubuntu/agent-data/projects/<project-name>/memory/short_term.md 2>/dev/null
cat /home/ubuntu/agent-data/projects/<project-name>/memory/long_term.md 2>/dev/null
```

### Step 5: 讀取專案結構
```bash
ls -F /home/ubuntu/<project-name>/
cat /home/ubuntu/<project-name>/README.md 2>/dev/null | head -n 30
```

### Step 6: 回報並等待指令
向用戶總結：
1. 專案名稱與簡介
2. 最後工作狀態 (Last Status)
3. 最近的活動日誌 (Activity Log)
4. 待辦事項 (Todo List)

然後詢問：「你想從哪裡開始？」

---

## 📋 可用專案清單
以下是目前已註冊的所有專案 (位於 /home/ubuntu/agent-data/projects/)：

| 專案名稱 | 代碼路徑 |
| :--- | :--- |
| ai-command-center | /home/ubuntu/agentmanager |
| asset-master | /home/ubuntu/asset-master |
| beauty-pk | /home/ubuntu/beauty-pk |
| groupbuy | (Remote Only) |
| history-synthesizer | /home/ubuntu/history-synthesizer |
| if-tv-station | /home/ubuntu/if-tv-station |
| moltbot | /home/ubuntu/moltbot |
| n8n-automation | /home/ubuntu/n8n-automation |
| openclaw | /home/ubuntu/openclaw |
| privacy-guard | /home/ubuntu/privacy-guard |
| redmine-issue-helper | /home/ubuntu/redmine-issue-helper |
| telegram-commander | /home/ubuntu/agentmanager/projects/telegram-commander |
| y2help-web | /home/ubuntu/y2help-web |
| y2helper | /home/ubuntu/y2helper |
| zeus-writer | /home/ubuntu/zeus-writer |
