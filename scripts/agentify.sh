#!/bin/bash
PROJECT_PATH=$(realpath "$1")
PROJECT_NAME=$(basename "$PROJECT_PATH")
CENTER_PATH="${AGENT_PROJECT_ROOT:-$(dirname "$(realpath "$0")")/..}"

echo "注入 AI DNA 到專案: $PROJECT_NAME..."

# 建立 .agent 軟連結 (全域規則注入)
mkdir -p "$PROJECT_PATH/.agent"
ln -sf "$CENTER_PATH"/.agent/* "$PROJECT_PATH/.agent/"

# Register mutable STATUS/memory in the data layer. The registrar intentionally
# creates no executable task until one satisfies the shared task contract.
python3 "$CENTER_PATH/scripts/register_project.py" "$PROJECT_NAME" \
    --display-name "$PROJECT_NAME" \
    --status "🆕 Initialized" \
    --summary "Project integrated via agentify.sh; executable tasks require workspace= and acceptance=."

# 在中心建立連結
ln -sf "$PROJECT_PATH" "$CENTER_PATH/projects/$PROJECT_NAME"

echo "✅ $PROJECT_NAME 已代理化並成功註冊至指揮中心。"
