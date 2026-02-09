# 🚀 推送到 GitHub 快速指令

## 📋 前置準備

### 1. 在 GitHub 創建倉庫（手動操作）

請前往：https://github.com/new

填寫以下資訊：
- **Repository name**: `shared-agent-skills`
- **Description**: `Shared AI agent skills for Antigravity workspace management - 支援跨平台（Windows/macOS/Linux）`
- **Visibility**: 🔒 **Private**（重要！）
- **不要勾選** "Initialize this repository with a README"

點擊 **Create repository**

---

## 🎯 推送指令

### 在 Git Bash / Terminal 執行：

```bash
cd d:/AgentManager/shared-agent-skills

# 添加遠端倉庫
git remote add origin https://github.com/alstonhuang/shared-agent-skills.git

# 重命名分支為 main
git branch -M main

# 推送到 GitHub
git push -u origin main
```

---

## ✅ 驗證推送成功

```bash
# 檢查遠端設定
git remote -v

# 應該看到：
# origin  https://github.com/alstonhuang/shared-agent-skills.git (fetch)
# origin  https://github.com/alstonhuang/shared-agent-skills.git (push)

# 查看 commit 歷史
git log --oneline -5
```

在瀏覽器前往 https://github.com/alstonhuang/shared-agent-skills 確認檔案已上傳。

應該看到：
- ✅ README.md
- ✅ CROSS_PLATFORM_GUIDE.md
- ✅ command_center_reporter/
- ✅ task_architect/
- ✅ workspace_manager/
- ✅ scripts/install.py
- ✅ scripts/init-workspace.sh

---

## 🔄 推送後的下一步

### 1. 更新 AgentManager 使用 Git 版本

```bash
# 備份現有 skills
cp -r d:/AgentManager/.agent/skills d:/AgentManager/.agent/skills.backup.$(date +%Y%m%d)

# 刪除舊版本
rm -rf d:/AgentManager/.agent/skills

# 從 GitHub 克隆新版本
git clone https://github.com/alstonhuang/shared-agent-skills.git d:/AgentManager/.agent/skills

# 驗證
ls d:/AgentManager/.agent/skills
```

### 2. 在新 Workspace 測試

在遠端 VM 或新環境：

```bash
# 創建新 workspace
mkdir test-workspace
cd test-workspace

# 使用 bash 腳本初始化
bash <(curl -s https://raw.githubusercontent.com/alstonhuang/shared-agent-skills/main/scripts/init-workspace.sh)

# 或手動克隆
git clone https://github.com/alstonhuang/shared-agent-skills.git .agent/skills

# 驗證安裝
python .agent/skills/scripts/install.py --list
```

---

## 📝 未來更新 Skills

```bash
# 1. 在本地修改 skills
cd d:/AgentManager/shared-agent-skills
# ... 修改檔案 ...

# 2. 提交變更
git add .
git commit -m "Update: 描述你的修改"
git push

# 3. 在其他 workspace 同步
cd /path/to/other/workspace/.agent/skills
git pull
```

---

## 🎉 完成！

推送成功後，你就擁有了：
- ✅ 跨平台的 Skills 管理系統
- ✅ Git 版本控制
- ✅ 可在任何環境快速部署
- ✅ 統一的虛擬根架構

**準備好了嗎？開始推送吧！** 🚀
