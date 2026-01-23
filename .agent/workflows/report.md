---
description: Report current project status to AI Command Center
---

# /report - Auto-Report Status to Command Center

This command makes you **automatically summarize and report** your work to the AI Command Center.
You DO NOT need the user to tell you what to report - you should figure it out yourself!

## How It Works

### 1. Identify Project
Use the current workspace folder name as the project name.

### 2. Load Token (One-time Setup)
Check for `.gh_token` file or ask user once and save it.

### 3. Fetch Previous Status (Important!)
Before reporting, fetch the project's current STATUS.md from GitHub to see:
- What was the last reported status?
- What were the last few log entries?

```python
# Fetch current status from Command Center
try:
    status_content = r.get_contents(f"projects/{PROJECT}/STATUS.md").decoded_content.decode("utf-8")
    # Parse to understand what was already reported
except:
    status_content = None  # First time - no previous status
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
```python
# Auto-register if needed
reporter.register(PROJECT, project_type="🖥️", link="(Local)")

# Log the auto-generated summary
reporter.log(PROJECT, "YOUR_AUTO_GENERATED_SUMMARY", level="INFO")

# Update status if significant milestone
reporter.update_status(PROJECT, "🚧 In Progress")  # or ✅ Done, ❌ Blocked
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
- **DO NOT** use git clone - use GitHub API only
- **DO** read previous STATUS.md to avoid duplicate reports
- **DO** be concise - summarize, don't dump everything
