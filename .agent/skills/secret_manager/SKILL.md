---
name: secret_manager
description: 整合 GitHub Organization Secrets，實現自動化的密鑰管理與同步。
---

# Secret Manager Skill

## 🎯 目的

使 Agent 能安全地從 GitHub Organization 獲取 Secrets (密鑰)，並自動將其注入本地開發環境（如 `.env` 檔案），減少手動配置密鑰的錯誤。

---

## 🚀 功能

### 1. **列出組織密鑰 (List Org Secrets)**
查看當前 Organization 下可用的 Secrets 列表（僅名稱，非內容）：
```bash
# Workflow 內部指令
gh secret list --org alston-personal
```

### 2. **獲取並同步密鑰 (Sync Secrets)**
將特定 Repo 的 Secrets 或 Org 級別的 Secrets 讀取並寫入本地 `.env`：
```bash
# 範例邏輯
gh secret get <SECRET_NAME> --org alston-personal
```

### 3. **檢查 .env 完整性**
自動掃描 `.env.example` 或代碼中的環境變數需求，並從 Organization 尋找補全。

---

## 📋 使用方法

### 取得 Organization Secrets 列表

Agent 應執行執行以下指令來確認哪些 Key 是可用的：
```bash
export GITHUB_TOKEN=$(cat /home/ubuntu/agentmanager/.gh_token)
gh secret list --org alston-personal
```

### 將 Secrets 寫入本地 .env

當發現專案缺少必要的 API Key 時，應執行：
```bash
# 虛擬碼邏輯：由 Agent 呼叫 gh 獲取並 append 到 .env
export GITHUB_TOKEN=$(cat /home/ubuntu/agentmanager/.gh_token)
KEY_VALUE=$(gh api /orgs/alston-personal/actions/secrets/SECRET_NAME --jq .value) # 需注意權限與安全性
```
> [!IMPORTANT]
> GitHub API 的加密 Secrets 無法直接透過 API 獲取明文。此 Skill 建議的實作方式是透過 `gh` 指令在 Action 環境或透過預先儲存的加密路徑讀取，或者提醒使用者進行手動同步。

---

## 🔧 命令列操作範例

```bash
# 查看所有秘密
gh secret list --org alston-personal

# 查看特定 Repo 的秘密
gh secret list --repo alston-personal/zeus-writer
```

---

## ⚠️ 安全規範

1.  **禁止日誌洩露**：絕不可在對話紀錄或終端日誌中印出密鑰明文。
2.  **檔案排除**：確保 `.env` 始終在 `.gitignore` 中。
3.  **Token 保護**：使用 `.gh_token` 檔案中的 Token 進行認證，不可將 Token 硬編碼。
