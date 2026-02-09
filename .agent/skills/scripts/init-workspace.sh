#!/usr/bin/env bash
# 新 Workspace 初始化腳本（跨平台）
# 適用於：Windows (Git Bash), macOS, Linux
#
# 使用方法：
#   bash init-workspace.sh
#   bash init-workspace.sh --name "MyWorkspace"

set -e  # 遇到錯誤立即退出

# 顏色定義
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# 預設值
SKILLS_REPO="https://github.com/alstonhuang/shared-agent-skills.git"
WORKSPACE_NAME=""
WORKSPACE_ROOT=$(pwd)

# 列印函數
print_header() {
    echo -e "\n${CYAN}========================================${NC}"
    echo -e "${CYAN}  $1${NC}"
    echo -e "${CYAN}========================================${NC}\n"
}

print_success() {
    echo -e "${GREEN}✅ $1${NC}"
}

print_error() {
    echo -e "${RED}❌ $1${NC}"
}

print_warning() {
    echo -e "${YELLOW}⚠️  $1${NC}"
}

print_info() {
    echo -e "${BLUE}ℹ️  $1${NC}"
}

# 解析參數
while [[ $# -gt 0 ]]; do
    case $1 in
        --name)
            WORKSPACE_NAME="$2"
            shift 2
            ;;
        --repo)
            SKILLS_REPO="$2"
            shift 2
            ;;
        --help)
            echo "用法: bash init-workspace.sh [選項]"
            echo ""
            echo "選項:"
            echo "  --name NAME    指定 workspace 名稱"
            echo "  --repo URL     指定 skills Git 倉庫 URL"
            echo "  --help         顯示此說明"
            echo ""
            echo "範例:"
            echo "  bash init-workspace.sh --name \"MyWorkspace\""
            exit 0
            ;;
        *)
            print_error "未知參數: $1"
            echo "使用 --help 查看說明"
            exit 1
            ;;
    esac
done

# 主要邏輯
print_header "Workspace 初始化工具"

echo "作業系統: $(uname -s)"
echo "Workspace 路徑: $WORKSPACE_ROOT"
echo ""

# 1. 檢查 Git
print_info "檢查 Git 安裝狀態..."
if ! command -v git &> /dev/null; then
    print_error "Git 未安裝"
    print_info "請前往 https://git-scm.com/downloads 安裝 Git"
    exit 1
fi
print_success "Git 已安裝: $(git --version)"
 
# 1.1 設定 Git 身分
print_info "設定 Git 預設身分..."
git config --global user.email "alston.huang@vivotek.com"
git config --global user.name "Alston"
print_success "Git 身分已設定為: Alston <alston.huang@vivotek.com>"

# 2. 創建目錄結構
print_info "創建目錄結構..."
mkdir -p .agent/workflows
mkdir -p memory
mkdir -p projects
print_success "目錄結構已創建"

# 3. 安裝 Skills
print_info "安裝 Shared Skills..."

if [ -d ".agent/skills" ]; then
    if [ -d ".agent/skills/.git" ]; then
        print_warning "Skills 已存在，執行更新..."
        cd .agent/skills
        git pull
        cd "$WORKSPACE_ROOT"
        print_success "Skills 已更新"
    else
        print_warning "Skills 目錄已存在但不是 Git 倉庫"
        read -p "是否要備份並重新安裝？(y/N): " -n 1 -r
        echo
        if [[ $REPLY =~ ^[Yy]$ ]]; then
            BACKUP_DIR=".agent/skills.backup.$(date +%Y%m%d_%H%M%S)"
            print_info "備份到: $BACKUP_DIR"
            mv .agent/skills "$BACKUP_DIR"
            git clone "$SKILLS_REPO" .agent/skills
            print_success "Skills 已重新安裝"
        else
            print_warning "跳過 Skills 安裝"
        fi
    fi
else
    git clone "$SKILLS_REPO" .agent/skills
    print_success "Skills 已安裝"
fi

# 4. 設定語言偏好
print_info "設定語言偏好..."
cat > .agent/LANGUAGE_PREFERENCE.md << 'EOF'
# 語言偏好設定

## 主要溝通語言
**繁體中文（Traditional Chinese, zh-TW）**

## 規則
1. 所有 AI 回應必須使用繁體中文
2. 代碼註解使用繁體中文
3. 文檔使用繁體中文
4. 禁止使用簡體中文

---

此設定適用於此 workspace 的所有對話。
EOF
print_success "語言偏好已設定為繁體中文"

# 5. 創建記憶檔案
print_info "創建長期記憶檔案..."
cat > memory/LONG_TERM.md << EOF
# Workspace 長期記憶

## 建立時間
$(date '+%Y-%m-%d %H:%M:%S')

## Workspace 資訊
- 名稱: ${WORKSPACE_NAME:-未指定}
- 位置: $WORKSPACE_ROOT
- 機器: $(hostname)
- 作業系統: $(uname -s)

## 已安裝的 Skills
EOF

# 列出已安裝的 skills
if [ -d ".agent/skills" ]; then
    for skill_dir in .agent/skills/*/; do
        if [ -f "${skill_dir}SKILL.md" ]; then
            skill_name=$(basename "$skill_dir")
            echo "- $skill_name" >> memory/LONG_TERM.md
        fi
    done
fi

cat >> memory/LONG_TERM.md << EOF

## 語言設定
- 主要語言: 繁體中文

## 專案列表
（待添加）
EOF

print_success "長期記憶檔案已創建"

# 6. 創建 .gitignore（如果不存在）
if [ ! -f ".gitignore" ]; then
    print_info "創建 .gitignore..."
    cat > .gitignore << 'EOF'
# 敏感資訊
.env
.gh_token
*.token

# Python
__pycache__/
*.pyc
*.pyo
*.pyd
.Python
venv/
env/

# Node.js
node_modules/
npm-debug.log
yarn-error.log

# IDE
.vscode/
.idea/
*.swp
*.swo

# 作業系統
.DS_Store
Thumbs.db
Desktop.ini

# 臨時檔案
*.tmp
*.bak
*.backup
EOF
    print_success ".gitignore 已創建"
fi

# 7. 列出已安裝的 Skills
print_header "已安裝的 Skills"
if [ -d ".agent/skills" ]; then
    for skill_dir in .agent/skills/*/; do
        if [ -f "${skill_dir}SKILL.md" ]; then
            skill_name=$(basename "$skill_dir")
            # 嘗試讀取描述
            desc=$(grep -A 1 "^description:" "${skill_dir}SKILL.md" | tail -n 1 | sed 's/description: //' | xargs)
            echo -e "${GREEN}  ✓ $skill_name${NC}"
            if [ -n "$desc" ]; then
                echo "    $desc"
            fi
        fi
    done
else
    print_warning "未找到 skills 目錄"
fi

# 完成
print_header "初始化完成"
print_success "Workspace 已成功初始化！"
echo ""
print_info "目錄結構："
echo "  .agent/skills/     - AI Skills"
echo "  .agent/workflows/  - Workflows（需手動添加）"
echo "  memory/            - 記憶系統"
echo "  projects/          - 專案目錄"
echo ""
print_info "下一步："
echo "  1. 重新啟動 Antigravity"
echo "  2. 開始使用 skills（查看 .agent/skills/*/SKILL.md）"
echo ""

# 提示如何更新 skills
print_info "更新 skills 的方法："
echo "  cd .agent/skills"
echo "  git pull"
echo ""

# 如果指定了 workspace 名稱，提示註冊
if [ -n "$WORKSPACE_NAME" ]; then
    print_info "註冊到 AI Command Center："
    echo "  使用 workspace_manager skill 註冊此 workspace"
    echo ""
fi

print_success "設定完成！享受使用 Antigravity 🚀"
