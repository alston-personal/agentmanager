---
description: Report current project status to AI Command Center
---

# /report - Auto-Report Status to Command Center

This command makes you **automatically summarize and report** your work to the AI Command Center.
You DO NOT need the user to tell you what to report - you should figure it out yourself!

## Architecture Guardrail

`/report` belongs to the logic layer, but it must write project state only to the data layer:

- Logic repo: `/home/ubuntu/agentmanager`
- Data repo: `/home/ubuntu/agent-data`

If the project is missing, call the local registration script first:

```bash
python3 scripts/register_project.py <project-name> --display-name "Project Name"
```

## How It Works

### 1. Identify Project
Use the current workspace folder name as the project name.

### 2. Verify Local Data-Layer Registration
Check whether the project already exists in:

```bash
/home/ubuntu/agent-data/projects/<project-name>/STATUS.md
```

If not, register it through the local script before reporting.

### 3. Fetch Previous Status (Important!)
Before reporting, read the local data-layer `STATUS.md` to see:
- What was the last reported status?
- What were the last few log entries?

```bash
cat /home/ubuntu/agent-data/projects/<project-name>/STATUS.md
```

### 4. Auto-Generate Report Content

**If First Time (no previous status):**
- Summarize the current state of the project based on your conversation history
- Example: "Initial setup: Created project structure, implemented authentication"

**If Has Previous Status:**
- Compare what you've done in THIS conversation vs what's already logged
- Report ONLY the NEW accomplishments
- Example: "Fixed username validation bug, added Back button to login screen"

**How to Generate Summary:**
1. Review the conversation history since your session started
2. List key accomplishments (code changes, fixes, new features)
3. Note any blockers or issues encountered
4. Condense into 1-2 sentences

### 5. Execute Report
```bash
# Auto-register if needed
python3 scripts/register_project.py <project-name> --display-name "Project Name"

# Then update data-layer status/logs using the project status file
```

### 6. Confirm to User
Tell user:
> "✅ 已回報至 AI Command Center:
> 專案: {PROJECT}
> 摘要: {YOUR_SUMMARY}"

## Example Behavior

**User says:** `/report`

**You should respond:**
> "📤 正在回報至 AI Command Center...
> 
> 📋 自動摘要:
> - 完成 Username 驗證修復
> - 新增 Login 頁面的 Back 按鈕
> - 修復導航返回邏輯
> 
> ✅ 已成功回報！"

## ⚠️ IMPORTANT
- **DO NOT** ask user "what do you want to report" - figure it out yourself!
- **DO** keep logic in `agentmanager` and status in `agent-data`
- **DO** read previous `STATUS.md` to avoid duplicate reports
- **DO** be concise - summarize, don't dump everything
