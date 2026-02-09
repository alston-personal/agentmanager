# 🌍 跨平台使用指南

## 📌 關於跨平台相容性

所有腳本和工具都設計為跨平台相容，支援：
- ✅ **Windows** - 通過 Git Bash（Git for Windows 內建）
- ✅ **macOS** - 原生支援
- ✅ **Linux** - 原生支援

---

## 🎯 不需要 Cygwin！

### Windows 使用者：只需安裝 Git for Windows

**Git for Windows** 已經包含完整的 Unix-like 環境：

1. **下載安裝 Git for Windows**
   - 網址：https://git-scm.com/download/win
   - 下載並執行安裝程式
   - 使用預設設定即可

2. **安裝後你會得到**：
   - Git Bash - 完整的 bash shell
   - 常用 Unix 工具（ls, grep, sed, awk, curl, ssh 等）
   - 與 macOS/Linux 相容的環境

3. **使用方式**：
   - 右鍵點選資料夾 → "Git Bash Here"
   - 或從開始選單啟動 "Git Bash"

---

## 🛠️ 可用的腳本格式

### 1. Python 腳本（推薦）✨

**優點**：
- 完全跨平台
- Antigravity 環境必有 Python
- 功能強大，易於維護

**使用範例**：
```bash
# Windows, macOS, Linux 都相同
python scripts/install.py --from-git
python scripts/install.py --list
```

**已提供的 Python 腳本**：
- `scripts/install.py` - Skills 安裝工具
- `workspace_manager/workspace_manager_client.py` - Workspace 管理
- `command_center_reporter/reporter_client.py` - 狀態回報

---

### 2. Bash Script

**使用方式**：

**Windows（Git Bash）**：
```bash
bash scripts/init-workspace.sh
bash scripts/init-workspace.sh --name "MyWorkspace"
```

**macOS / Linux**：
```bash
./scripts/init-workspace.sh
# 或
bash scripts/init-workspace.sh
```

**已提供的 Bash 腳本**：
- `scripts/init-workspace.sh` - Workspace 初始化

---

### 3. 直接使用 Git 命令（最簡單）

適用於簡單操作，所有平台都相同：

```bash
# 安裝 skills
git clone https://github.com/alstonhuang/shared-agent-skills.git .agent/skills

# 更新 skills
cd .agent/skills
git pull

# 查看版本
git log -1 --oneline
```

---

## 🚀 快速開始指南

### Windows 使用者

```bash
# 1. 開啟 Git Bash（右鍵 → Git Bash Here）

# 2. 初始化 workspace
cd /d/your-workspace
bash init-workspace.sh

# 或使用 Python 腳本
python scripts/install.py --from-git
```

### macOS / Linux 使用者

```bash
# 1. 開啟 Terminal

# 2. 初始化 workspace
cd ~/your-workspace
bash init-workspace.sh

# 或使用 Python 腳本
python3 scripts/install.py --from-git
```

---

## 📁 路徑表示法

### 跨平台路徑處理

**Python 腳本自動處理**：
```python
from pathlib import Path

# 自動適配 Windows/Unix 路徑
path = Path(".agent") / "skills"
# Windows: .agent\skills
# Unix: .agent/skills
```

**Bash 腳本使用 Unix 風格**：
```bash
# Git Bash 會自動轉換
cd .agent/skills

# Windows 路徑轉換範例
# C:\Users\user\workspace → /c/Users/user/workspace
# D:\AgentManager → /d/AgentManager
```

---

## 🔧 工具對照表

| 功能 | Windows (Git Bash) | macOS / Linux |
|------|-------------------|---------------|
| Python 3 | `python` 或 `python3` | `python3` |
| Bash Shell | Git Bash | Terminal |
| 列出檔案 | `ls` | `ls` |
| 搜尋 | `grep` | `grep` |
| 複製 | `cp` | `cp` |
| 移動 | `mv` | `mv` |
| 刪除 | `rm` | `rm` |
| Git | `git` | `git` |

---

## ⚙️ 環境變數設定

### Windows (Git Bash)

```bash
# 臨時設定（當前 session）
export GITHUB_TOKEN="your_token_here"

# 永久設定（加到 ~/.bashrc）
echo 'export GITHUB_TOKEN="your_token_here"' >> ~/.bashrc
source ~/.bashrc
```

### macOS / Linux

```bash
# 臨時設定
export GITHUB_TOKEN="your_token_here"

# 永久設定（加到 ~/.bashrc 或 ~/.zshrc）
echo 'export GITHUB_TOKEN="your_token_here"' >> ~/.bashrc
source ~/.bashrc
```

### 所有平台通用：使用 .env 檔案

```bash
# 創建 .env 檔案
cat > .env << EOF
GITHUB_TOKEN=your_token_here
GITHUB_REPO=alstonhuang/AI_Command_Center
EOF

# Python 腳本會自動讀取（使用 python-dotenv）
```

---

## 🎨 最佳實踐

### 1. 使用 Python 進行複雜邏輯
```python
# ✅ 好的做法
python scripts/install.py --from-git

# 功能強大，完全跨平台
```

### 2. 使用 Bash 進行簡單自動化
```bash
# ✅ 好的做法
bash scripts/init-workspace.sh

# 簡單直接，Git Bash 完全支援
```

### 3. 直接使用 Git 命令
```bash
# ✅ 最簡單的做法
git clone https://github.com/alstonhuang/shared-agent-skills.git .agent/skills
cd .agent/skills
git pull
```

### 4. 避免使用的做法
```powershell
# ❌ PowerShell 專有指令（不跨平台）
Copy-Item -Recurse source destination

# ✅ 改用 bash/Python
cp -r source destination
```

---

## 🧪 測試跨平台相容性

### 驗證 Git Bash（Windows）

```bash
# 在 Git Bash 中執行以下命令
uname -s          # 應顯示 MINGW64_NT...
which python      # 應找到 Python
which git         # 應找到 Git
bash --version    # 應顯示 bash 版本
```

### 驗證 Python 環境

```bash
# 所有平台
python --version  # 或 python3 --version
python -c "import sys; print(sys.platform)"
# Windows: win32
# macOS: darwin
# Linux: linux
```

---

## 📚 參考資源

### Git for Windows
- 官網：https://git-scm.com/download/win
- 文檔：https://git-scm.com/docs

### Python
- 官網：https://www.python.org/
- Windows 安裝：https://www.python.org/downloads/windows/

### Bash 教學
- GNU Bash：https://www.gnu.org/software/bash/
- Bash 腳本教學：https://www.shellscript.sh/

---

## 🆘 常見問題

### Q: Windows 上找不到 `bash` 命令
**A**: 請安裝 Git for Windows，它包含 Git Bash。

### Q: 如何在 Windows 使用 Unix 風格的路徑？
**A**: Git Bash 自動處理。例如 `C:\Users` 在 Git Bash 中是 `/c/Users`。

### Q: Python 腳本在 Windows 無法執行
**A**: 確保 Python 已安裝並在 PATH 中。使用 `python --version` 檢查。

### Q: 權限錯誤（Permission denied）
**A**: 
```bash
# macOS/Linux: 添加執行權限
chmod +x scripts/init-workspace.sh

# Windows Git Bash: 通常不需要，直接用 bash 執行
bash scripts/init-workspace.sh
```

---

## ✅ 總結

### 跨平台策略

1. **優先使用 Python** - 完全跨平台，功能強大
2. **Bash 適合簡單任務** - Git Bash 在 Windows 也能用
3. **直接用 Git 命令** - 最簡單通用的方式
4. **避免 PowerShell** - 不跨平台（除非你只在 Windows 上用）

### Windows 使用者只需要

- ✅ Git for Windows（含 Git Bash）
- ✅ Python 3
- ❌ 不需要 Cygwin
- ❌ 不需要 WSL

**這樣就能享受完整的跨平台開發體驗！** 🚀
