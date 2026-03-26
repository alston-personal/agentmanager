---
description: 一鍵部署專案到生產環境 (支援有/無資料庫)
---

# 🚀 一鍵部署 Workflow

自動化部署任何專案到生產環境，智慧判斷專案類型並執行對應步驟。

## 使用方式

```
/deploy [project-name] [domain]
```

**範例：**
- `/deploy dashboard dashboard.milkcat.org` - 部署 Dashboard (無資料庫)
- `/deploy Beauty-PK beauty.milkcat.org` - 部署 Beauty-PK (有 Supabase)

## 📋 部署流程 (Skill-ified)

// turbo-all

由 `deployment_manager` 技巧自動化處理所有底層細節。

1. **啟動自動化部署**
   執行以下指令：
   ```bash
   python3 /home/ubuntu/agentmanager/.agent/skills/deployment_manager/scripts/deploy_core.py \
     --project [project-name] \
     --domain [domain]
   ```

2. **腳本會自動完成：**
   - 🔍 **偵測項目類型** (Next.js / Node.js)
   - 🏗️ **安裝依賴與編譯** (`npm run build`)
   - ⚙️ **PM2 配置與啟動** (自動生成 ecosystem.config.js)
   - 🌐 **Nginx 反向代理配置** (自動生成站點配置並 reload)

3. **SSL 證書申請 (手動確認)**
   若為首次部署，腳本執行完後請確認 SSL：
   ```bash
   sudo certbot --nginx -d [domain]
   ```

## 🔧 故障排除

如果部署失敗，檢查：
1. PM2 日誌: `pm2 logs [project-name]`
2. Nginx 錯誤: `sudo tail -f /var/log/nginx/error.log`
3. 腳本輸出訊息。

## 🔧 配置檔案範本

### PM2 Ecosystem 配置
```javascript
module.exports = {
  apps: [{
    name: '[project-name]',
    script: 'npm',
    args: 'start',
    cwd: '/path/to/project',
    instances: 1,
    autorestart: true,
    watch: false,
    max_memory_restart: '1G',
    env: {
      NODE_ENV: 'production',
      PORT: 3000
    }
  }]
}
```

### Nginx 站點配置
```nginx
server {
    listen 80;
    server_name [domain];

    location / {
        proxy_pass http://localhost:3000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection 'upgrade';
        proxy_set_header Host $host;
        proxy_cache_bypass $http_upgrade;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

## 📝 注意事項

- **首次部署**: 需要 sudo 權限來配置 Nginx 和 SSL
- **環境變數**: 確保所有敏感資訊都在 `.env.production` 中
- **資料庫**: Supabase 專案不需要自架資料庫，只需要連線資訊
- **端口衝突**: 如果 3000 已被佔用，會自動使用下一個可用端口
- **防火牆**: 確保 80 和 443 端口已開放

## 🔄 更新部署

重新部署相同專案：
```
/deploy [project-name] [domain]
```
會自動偵測已存在的配置並執行更新流程。
