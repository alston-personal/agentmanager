# 🛠️ Shared Agent Skills

> **🤖 For Antigravity AI (Auto-Setup Instruction):**
> 如果用戶給你這個連結並要求設定環境，請按照以下步驟執行：
> 1.  **Workspace 確認**：確認安裝路徑。
> 2.  **環境診斷**：檢查 `git` 與 `python`。
> 3.  **參數獲取 (安全讀取模式)**：
>     -   優先讀取現有 `.env`。若無，則向用戶索取 **Token** 與 **倉庫路徑**。
> 4.  **建立結構與設定**：
>     -   執行 Git Bash 命令 `mkdir -p .agent/workflows memory projects`。
>     -   **自動建立配置**：建立 `.env`, `.gh_token`, `config.json`。
>     -   **設定 Git 身分**：執行 `git config --global user.email "alston.huang@vivotek.com"` 與 `git config --global user.name "Alston"` 以避免提交失敗。
>     -   **自動化克隆 (免代碼模式)**：
>         -   使用 `git clone https://{TOKEN}@github.com/alstonhuang/shared-agent-skills.git .agent/skills`。
>         -   使用 `git clone https://{TOKEN}@github.com/{COMMAND_CENTER_REPO}.git temp_cc`。
>         -   這樣可以避開互動式驗證，直接完成下載。
>     -   部署規則與 `DASHBOARD.md`。
> 5.  **批量搬移專案**：使用 Token 批量同步所有專案。
> 6.  **回報進度**：回傳「✅ 搬家完成！已透過 Token 自動通過驗證，無須手動輸入代碼。」
> ---

這個倉庫包含可跨 workspace 共享的 Antigravity AI Skills。

## 📦 已包含的 Skills

### 1. Command Center Reporter
**描述**：讓 AI 代理能夠透過 GitHub API 向中央 AI Command Center 回報狀態。

**主要功能**：
- 註冊新專案到 Command Center
- 記錄專案活動日誌
- 更新專案狀態
- 避免使用 git clone，直接使用 GitHub API

**使用方法**：
```python
from reporter_client import ProjectReporter

reporter = ProjectReporter(TOKEN, "alstonhuang/AI_Command_Center")
reporter.register("YourProjectName")
reporter.log("YourProjectName", "Complete feature X")
reporter.update_status("YourProjectName", "🚧 Working")
```

---

### 2. Task Architect
**描述**：處理專案規劃、技術規格撰寫和任務分解。

**主要功能**：
- 生成技術規格文件 (SPEC.md)
- 創建任務清單 (TASKS.md)
- 自動更新專案狀態
- 與 Dashboard 整合

**使用方法**：
使用 `/plan` workflow 來啟動專案規劃流程。

---

## 🌍 跨平台支援

✅ **完全支援 Windows, macOS, Linux**

### ⚠️ Windows 使用者重要提示
- ✅ **使用 Git Bash**（隨 Git for Windows 安裝）
- ❌ **不要使用 PowerShell**（語法不相容）
- ❌ **不需要** Cygwin 或 WSL
- 所有腳本都能在 Git Bash 中執行

**為什麼使用 Git Bash？**
- ✅ 與 macOS/Linux 指令完全相容
- ✅ 支援所有 bash 腳本和 Unix 工具
- ✅ 跨平台統一，學一次到處用
- ❌ PowerShell 語法不同（如 `Copy-Item` vs `cp`）

**如何使用 Git Bash：**
- 方法 1: 右鍵點選資料夾 → "Git Bash Here"
- 方法 2: 開始選單搜尋 "Git Bash"

### 提供的腳本格式
1. **Python 腳本**（推薦）- 完全跨平台
2. **Bash 腳本** - Git Bash 完全支援
3. **直接使用 Git 命令** - 最簡單通用

📖 詳細說明請參考：[跨平台使用指南](CROSS_PLATFORM_GUIDE.md)

---

## 🚀 安裝方式

### 方法 1：在新 Workspace 使用 Git Clone
```bash
# 在 Git Bash (Windows) 或 Terminal (macOS/Linux) 執行
cd /path/to/your/workspace
mkdir -p .agent
git clone https://github.com/alstonhuang/shared-agent-skills.git .agent/skills
```

### 方法 2：使用自動化腳本（跨平台）

**選項 A：Python 腳本（推薦）**
```bash
# 從 Git 安裝（所有平台相同）
python scripts/install.py --from-git

# 列出已安裝的 skills
python scripts/install.py --list
```

**選項 B：Bash 初始化腳本**
```bash
# Windows: 開啟 Git Bash
# macOS/Linux: 開啟 Terminal

bash scripts/init-workspace.sh
# 或指定名稱
bash scripts/init-workspace.sh --name "MyWorkspace"
```

### 方法 3：符號連結（同一台機器，僅限本地）
```powershell
# Windows (需要管理員權限)
New-Item -ItemType SymbolicLink -Path ".agent\skills" -Target "d:\AgentManager\shared-agent-skills"
```

---

## 🔄 更新 Skills

在已安裝的 workspace 中：
```powershell
cd .agent/skills
git pull
```

---

## 📋 包含的 Workflows

除了 skills，這個倉庫也包含常用的 workflows：

### `/report` - 自動回報狀態
自動摘要當前工作並回報到 AI Command Center。

**功能**：
- 自動識別專案
- 讀取先前狀態，避免重複回報
- 智慧摘要新的工作內容
- 直接使用 GitHub API（不使用 git clone）

### `/status` - 查看所有專案狀態
從 AI Command Center 讀取所有專案的狀態。

**功能**：
- 顯示 Dashboard 總覽
- 列出每個專案的詳細狀態
- 顯示最近活動記錄

### 安裝 Workflows
```bash
# 複製到你的 workspace
cp workflows/*.md /path/to/your/workspace/.agent/workflows/
```

---

## 📝 開發新 Skill

每個 skill 必須包含：
1. **SKILL.md** - 包含 YAML frontmatter 和說明文件
   ```yaml
   ---
   name: your_skill_name
   description: 簡短描述
   ---
   ```
2. **腳本檔案** - 如 Python、PowerShell 等
3. **範例或測試** (選用)

---

## 🌐 語言設定

此倉庫的文檔和註解使用**繁體中文**。

---

## 📄 授權

私有倉庫，僅供個人使用。

---

## 🔗 相關連結

- [AI Command Center](https://github.com/alstonhuang/AI_Command_Center)
- [AgentManager 主專案](d:\AgentManager)
