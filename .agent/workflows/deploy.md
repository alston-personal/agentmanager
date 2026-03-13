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

## 📋 部署步驟

// turbo-all

1. **確認專案路徑**
   - 檢查專案是否存在於 workspace 或 dashboard 目錄
   - 驗證專案結構 (package.json, next.config.js)

2. **環境檢查**
   - 檢查 Node.js 版本 (需要 18+)
   - 檢查 npm/pnpm 是否安裝
   - 檢查 Nginx 是否已安裝
   - 檢查 PM2 是否已安裝 (若無則自動安裝)

3. **專案類型偵測**
   - 檢查是否有 `prisma/schema.prisma` (Prisma 資料庫)
   - 檢查是否有 `supabase` 相關設定 (Supabase)
   - 檢查 `.env.example` 中的資料庫變數

4. **環境變數配置**
   - 複製 `.env.example` 到 `.env.production`
   - 提示用戶填寫必要的環境變數
   - 驗證資料庫連線 (如果有使用資料庫)

5. **安裝依賴**
   ```bash
   cd /path/to/project
   npm install --production
   ```

6. **資料庫遷移** (僅當偵測到資料庫時)
   - Prisma: `npx prisma migrate deploy`
   - Supabase: 檢查連線並顯示遷移指引
   - 其他: 執行專案特定的遷移腳本

7. **建置生產版本**
   ```bash
   npm run build
   ```

8. **PM2 配置與啟動**
   - 建立 PM2 ecosystem 配置檔
   - 啟動或重啟應用
   ```bash
   pm2 start ecosystem.config.js
   pm2 save
   ```

9. **Nginx 反向代理配置**
   - 建立 Nginx 站點配置檔
   - 配置反向代理到 localhost:3000 (或指定端口)
   - 啟用站點並重載 Nginx
   ```bash
   sudo ln -s /etc/nginx/sites-available/[domain] /etc/nginx/sites-enabled/
   sudo nginx -t
   sudo systemctl reload nginx
   ```

10. **SSL 證書申請** (Let's Encrypt)
    ```bash
    sudo certbot --nginx -d [domain]
    ```

11. **健康檢查**
    - 等待 10 秒讓服務啟動
    - 檢查 PM2 狀態
    - 測試 HTTP/HTTPS 連線
    - 驗證 API 端點回應

12. **部署報告**
    - 顯示部署摘要
    - 列出訪問 URL
    - 提供 PM2 管理指令
    - 記錄到 AI Command Center

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

## 🛠️ 故障排除

如果部署失敗，檢查：
1. PM2 日誌: `pm2 logs [project-name]`
2. Nginx 錯誤: `sudo tail -f /var/log/nginx/error.log`
3. 環境變數: 確認 `.env.production` 配置正確
4. 端口佔用: `sudo lsof -i :3000`

## 🔄 更新部署

重新部署相同專案：
```
/deploy [project-name] [domain]
```
會自動偵測已存在的配置並執行更新流程。
