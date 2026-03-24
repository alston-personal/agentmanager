# 🚀 Agent OS Lite 重建指南 (Selective Migration)

此指南說明如何在不拉取所有專案的情況下，在另一台 Server 建立輕量化的 Agent OS 環境。

## 🔹 階段一：建立底層環境

在全新的 Server 上執行以下指令：

```bash
# 1. 克隆 Logic 層 (工具與指令)
git clone https://github.com/alston-personal/agentmanager.git /home/ubuntu/agentmanager

# 2. 克隆 Data 層 (元資料與記憶)
# 這包含所有專案的 project.yaml，但體積非常小
git clone https://github.com/alston-personal/my-agent-data.git /home/ubuntu/agent-data

# 3. 初始化環境身分 (建議執行)
cd /home/ubuntu/agentmanager
git config --global user.email "alston.huang@vivotek.com"
git config --global user.name "Alston"
```

## 🔹 階段三：納入這台 Server 上原有的專案

如果這台 Server 已經有一些運行中的專案，想納入管理：

```bash
# 將現有資料夾導入，並標記為 Work 分類
python3 scripts/import_project.py /home/ubuntu/my-existing-app --sector Work
```

---

## 🛠️ 維護建議

1.  **更新分類**：若要修改專案分類，請修改 `/home/ubuntu/agent-data/projects/[project-name]/project.yaml` 中的 `sector` 欄位。
2.  **同步狀態**：完成工作後，記得在該專案下執行 `/report` 將進度推回 GitHub，確保兩台 Server 看到的是最新的 `STATUS.md`。
