#!/bin/bash
PROJECT_PATH=$(realpath "$1")
PROJECT_NAME=$(basename "$PROJECT_PATH")
CENTER_PATH="${AGENT_PROJECT_ROOT:-$(dirname "$(realpath "$0")")/..}"

echo "注入 AI DNA 到專案: $PROJECT_NAME..."

# 建立 .agent 軟連結 (全域規則注入)
mkdir -p "$PROJECT_PATH/.agent"
ln -sf "$CENTER_PATH"/.agent/* "$PROJECT_PATH/.agent/"

# 建立 STATUS.md 如果不存在
if [ ! -f "$PROJECT_PATH/STATUS.md" ]; then
    cat <<EOM > "$PROJECT_PATH/STATUS.md"
# Project Status: $PROJECT_NAME

## 📍 Summary
| Metric | Value |
| :--- | :--- |
| **Last Status** | 🆕 Initialized |
| **Last Updated** | $(date '+%Y-%m-%d %H:%M:%S') |

## �� Activity Log (Latest on Top)
<!-- LOG_START -->
- \`$(date '+%Y-%m-%d %H:%M:%S')\` ℹ️ **INFO**: Project integrated into AI Command Center via agentify.sh
<!-- LOG_END -->

## 📅 Todo List
- [ ] Initial Task Analysis
EOM
fi

# 在中心建立連結
ln -sf "$PROJECT_PATH" "$CENTER_PATH/projects/$PROJECT_NAME"

echo "✅ $PROJECT_NAME 已代理化並成功註冊至指揮中心。"
