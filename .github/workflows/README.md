# GitHub Actions For n8n Deploy

這個資料夾目前包含：

- `deploy-n8n-env.yml`

用途是把 GitHub organization or repository secrets 同步到 n8n 主機的
`/home/ubuntu/n8n-automation/.env`，然後重啟 n8n container。

## 需要的 secrets

- `N8N_DEPLOY_HOST`
- `N8N_DEPLOY_USER`
- `N8N_DEPLOY_SSH_KEY`
- `N8N_DEPLOY_SSH_PORT`
- `N8N_API_KEY`
- `N8N_BASE_URL`
- `TG_BOT_SUNLAKE_CC_TOKEN`
- `TELEGRAM_CHANNEL_ID`
- `GEMINI_API_KEY`

## 目前行為

這個 workflow 會覆寫遠端的：

- `/home/ubuntu/n8n-automation/.env`

然後執行：

- `/home/ubuntu/n8n-automation/run_n8n.sh`

## 注意

這個 workflow 會先檢查必要 secrets 是否存在。
目前必填的是：

- `N8N_API_KEY`
- `N8N_BASE_URL`
- `TG_BOT_SUNLAKE_CC_TOKEN`
- `TELEGRAM_CHANNEL_ID`

`GEMINI_API_KEY` 目前會一併寫入 `.env`，但不是 fail 條件。
