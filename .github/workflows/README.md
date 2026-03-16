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
- `N8N_RUNTIME_ENV`

## `N8N_RUNTIME_ENV` 格式

請把整份 `.env` 內容存成一個 multi-line secret，例如：

```env
N8N_API_KEY=...
N8N_BASE_URL=https://n8n.milkcat.org
TG_BOT_SUNLAKE_CC_TOKEN=...
TELEGRAM_CHANNEL_ID=...
GEMINI_API_KEY=...
```

這樣 workflow 會把 secret 內容原樣寫到遠端 `.env`。

## 目前行為

這個 workflow 會覆寫遠端的：

- `/home/ubuntu/n8n-automation/.env`

然後執行：

- `/home/ubuntu/n8n-automation/run_n8n.sh`

## 注意

GitHub Actions 不能直接「列出並讀取全部 secrets」，所以無法自動把 organization secrets 全抓出來。
如果你要「全寫入」，正確做法是把整份執行時環境集中到 `N8N_RUNTIME_ENV` 這個 multi-line secret。
