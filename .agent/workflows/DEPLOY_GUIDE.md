# 🚀 一鍵部署使用指南

## 快速開始

### 部署 Dashboard (無資料庫)
```bash
bash .agent/workflows/scripts/deploy.sh dashboard dashboard.milkcat.org
```

### 部署 Beauty-PK (有 Supabase)
```bash
bash .agent/workflows/scripts/deploy.sh Beauty-PK beauty.milkcat.org
```

## 📋 部署前準備

### 1. 確認伺服器環境
- ✅ Ubuntu/Debian Linux
- ✅ Node.js 18+ 已安裝
- ✅ Nginx 已安裝
- ✅ 有 sudo 權限

### 2. 環境變數配置

**Dashboard (無資料庫):**
```env
# .env.production
JWT_SECRET=your-secret-key
ADMIN_USERNAME=admin
ADMIN_PASSWORD_HASH=
```

**Beauty-PK (有 Supabase):**
```env
# .env.production
NEXT_PUBLIC_SUPABASE_URL=https://your-project.supabase.co
NEXT_PUBLIC_SUPABASE_ANON_KEY=your-anon-key
SUPABASE_SERVICE_ROLE_KEY=your-service-role-key
LINE_CHANNEL_ID=your-line-channel-id
LINE_CHANNEL_SECRET=your-line-channel-secret
```

### 3. DNS 設定
確保域名已指向您的伺服器 IP：
```bash
# 檢查 DNS
nslookup dashboard.milkcat.org
```

## 🎯 部署流程

腳本會自動執行以下步驟：

1. ✅ 尋找專案目錄
2. ✅ 偵測專案類型 (有無資料庫)
3. ✅ 檢查/建立環境變數
4. ✅ 安裝依賴
5. ✅ 執行資料庫遷移 (如果需要)
6. ✅ 建置生產版本
7. ✅ 配置 PM2 進程管理
8. ✅ 配置 Nginx 反向代理
9. ✅ 申請 SSL 證書
10. ✅ 健康檢查

## 📊 部署後管理

### PM2 管理指令
```bash
# 查看所有服務
pm2 list

# 查看日誌
pm2 logs dashboard

# 重啟服務
pm2 restart dashboard

# 停止服務
pm2 stop dashboard

# 查看詳細資訊
pm2 show dashboard
```

### Nginx 管理
```bash
# 測試配置
sudo nginx -t

# 重載配置
sudo systemctl reload nginx

# 查看錯誤日誌
sudo tail -f /var/log/nginx/error.log
```

### SSL 證書更新
```bash
# 手動更新證書
sudo certbot renew

# 測試自動更新
sudo certbot renew --dry-run
```

## 🔧 故障排除

### 問題 1: 端口被佔用
```bash
# 查看端口佔用
sudo lsof -i :3000

# 腳本會自動尋找下一個可用端口
```

### 問題 2: PM2 服務無法啟動
```bash
# 查看詳細日誌
pm2 logs dashboard --lines 50

# 檢查環境變數
cat /path/to/project/.env.production
```

### 問題 3: Nginx 502 Bad Gateway
```bash
# 檢查 PM2 服務是否運行
pm2 list

# 檢查端口是否正確
sudo netstat -tlnp | grep 3000
```

### 問題 4: SSL 證書申請失敗
```bash
# 確認 DNS 已正確設定
nslookup your-domain.com

# 確認 80 端口可訪問
curl http://your-domain.com

# 手動申請證書
sudo certbot --nginx -d your-domain.com
```

## 🔄 更新部署

當專案有更新時，重新執行部署腳本即可：

```bash
# 會自動偵測已存在的配置並更新
bash .agent/workflows/scripts/deploy.sh dashboard dashboard.milkcat.org
```

腳本會：
- 重新建置專案
- 重啟 PM2 服務
- 保留現有的 Nginx 和 SSL 配置

## 📝 注意事項

1. **首次部署需要 sudo 權限** - 用於配置 Nginx 和 SSL
2. **環境變數安全** - 不要將 `.env.production` 提交到 Git
3. **資料庫備份** - 部署前建議備份資料庫
4. **防火牆設定** - 確保 80 和 443 端口已開放
5. **域名準備** - 部署前確保 DNS 已正確設定

## 🎉 成功部署後

訪問您的網站：
- HTTP: `http://your-domain.com` (會自動重定向到 HTTPS)
- HTTPS: `https://your-domain.com`

享受您的生產環境！🚀
