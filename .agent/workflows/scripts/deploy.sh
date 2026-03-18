#!/bin/bash

# 🚀 一鍵部署腳本
# 用途: 自動化部署 Next.js 專案到生產環境

set -e  # 遇到錯誤立即退出

# 顏色輸出
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# 函數: 輸出訊息
log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# 檢查參數
if [ $# -lt 2 ]; then
    log_error "使用方式: $0 <project-name> <domain>"
    log_info "範例: $0 dashboard dashboard.milkcat.org"
    exit 1
fi

PROJECT_NAME=$1
DOMAIN=$2
BASE_DIR="/home/ubuntu/agentmanager"
PROJECT_DIR=""

# 尋找專案目錄
log_info "尋找專案: $PROJECT_NAME"
if [ -d "$BASE_DIR/workspace/$PROJECT_NAME" ]; then
    PROJECT_DIR="$BASE_DIR/workspace/$PROJECT_NAME"
elif [ -d "$BASE_DIR/$PROJECT_NAME" ]; then
    PROJECT_DIR="$BASE_DIR/$PROJECT_NAME"
else
    log_error "找不到專案: $PROJECT_NAME"
    exit 1
fi

log_success "找到專案: $PROJECT_DIR"

# 檢查 package.json
if [ ! -f "$PROJECT_DIR/package.json" ]; then
    log_error "找不到 package.json"
    exit 1
fi

# 偵測專案類型
HAS_DATABASE=false
DB_TYPE=""

if [ -f "$PROJECT_DIR/prisma/schema.prisma" ]; then
    HAS_DATABASE=true
    DB_TYPE="Prisma"
    log_info "偵測到 Prisma 資料庫"
elif grep -q "supabase" "$PROJECT_DIR/package.json" 2>/dev/null; then
    HAS_DATABASE=true
    DB_TYPE="Supabase"
    log_info "偵測到 Supabase 資料庫"
fi

# 環境變數檢查
log_info "檢查環境變數..."
if [ ! -f "$PROJECT_DIR/.env.production" ]; then
    if [ -f "$PROJECT_DIR/.env.example" ]; then
        log_warning ".env.production 不存在，從 .env.example 複製"
        cp "$PROJECT_DIR/.env.example" "$PROJECT_DIR/.env.production"
        log_warning "請編輯 $PROJECT_DIR/.env.production 填寫正確的環境變數"
        read -p "按 Enter 繼續..."
    else
        log_warning "找不到 .env.example，跳過環境變數配置"
    fi
fi

# 安裝依賴
log_info "安裝依賴..."
cd "$PROJECT_DIR"
npm install

# 資料庫遷移 (如果需要)
if [ "$HAS_DATABASE" = true ]; then
    log_info "執行資料庫遷移 ($DB_TYPE)..."
    if [ "$DB_TYPE" = "Prisma" ]; then
        npx prisma migrate deploy
        npx prisma generate
    elif [ "$DB_TYPE" = "Supabase" ]; then
        log_info "Supabase 專案，跳過本地遷移"
    fi
fi

# 建置
log_info "建置生產版本..."
npm run build

# 檢查 PM2
if ! command -v pm2 &> /dev/null; then
    log_warning "PM2 未安裝，正在安裝..."
    sudo npm install -g pm2
fi

# 尋找可用端口
PORT=3000
while lsof -Pi :$PORT -sTCP:LISTEN -t >/dev/null 2>&1; do
    log_warning "端口 $PORT 已被佔用，嘗試下一個..."
    PORT=$((PORT + 1))
done
log_success "使用端口: $PORT"

# 建立 PM2 配置
log_info "建立 PM2 配置..."
cat > "$PROJECT_DIR/ecosystem.config.js" <<EOF
module.exports = {
  apps: [{
    name: '$PROJECT_NAME',
    script: 'npm',
    args: 'start',
    cwd: '$PROJECT_DIR',
    instances: 1,
    autorestart: true,
    watch: false,
    max_memory_restart: '1G',
    env: {
      NODE_ENV: 'production',
      PORT: $PORT
    }
  }]
}
EOF

# 啟動或重啟 PM2
log_info "啟動應用..."
if pm2 list | grep -q "$PROJECT_NAME"; then
    pm2 restart "$PROJECT_NAME"
else
    pm2 start "$PROJECT_DIR/ecosystem.config.js"
fi
pm2 save

# 建立 Nginx 配置
log_info "建立 Nginx 配置..."
NGINX_CONF="/etc/nginx/sites-available/$PROJECT_NAME"
sudo tee "$NGINX_CONF" > /dev/null <<EOF
server {
    listen 80;
    server_name $DOMAIN;

    location / {
        proxy_pass http://localhost:$PORT;
        proxy_http_version 1.1;
        proxy_set_header Upgrade \$http_upgrade;
        proxy_set_header Connection 'upgrade';
        proxy_set_header Host \$host;
        proxy_cache_bypass \$http_upgrade;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
    }
}
EOF

# 啟用站點
if [ ! -L "/etc/nginx/sites-enabled/$PROJECT_NAME" ]; then
    sudo ln -s "$NGINX_CONF" "/etc/nginx/sites-enabled/$PROJECT_NAME"
fi

# 測試 Nginx 配置
log_info "測試 Nginx 配置..."
sudo nginx -t

# 重載 Nginx
log_info "重載 Nginx..."
sudo systemctl reload nginx

# SSL 證書
log_info "申請 SSL 證書..."
if command -v certbot &> /dev/null; then
    sudo certbot --nginx -d "$DOMAIN" --non-interactive --agree-tos --email admin@milkcat.org || log_warning "SSL 證書申請失敗，請手動執行: sudo certbot --nginx -d $DOMAIN"
else
    log_warning "Certbot 未安裝，跳過 SSL 配置"
    log_info "安裝 Certbot: sudo apt install certbot python3-certbot-nginx"
fi

# 健康檢查
log_info "等待服務啟動..."
sleep 5

if pm2 list | grep -q "$PROJECT_NAME.*online"; then
    log_success "PM2 服務運行正常"
else
    log_error "PM2 服務啟動失敗"
    pm2 logs "$PROJECT_NAME" --lines 20
    exit 1
fi

# 部署完成
echo ""
log_success "========================================="
log_success "🎉 部署完成！"
log_success "========================================="
echo ""
log_info "專案名稱: $PROJECT_NAME"
log_info "訪問地址: https://$DOMAIN"
log_info "本地端口: $PORT"
log_info "專案路徑: $PROJECT_DIR"
echo ""
log_info "管理指令:"
log_info "  查看日誌: pm2 logs $PROJECT_NAME"
log_info "  重啟服務: pm2 restart $PROJECT_NAME"
log_info "  停止服務: pm2 stop $PROJECT_NAME"
log_info "  查看狀態: pm2 status"
echo ""
