#!/bin/bash

# Antigravity Git Security & Governance Guard
# 此腳本會掃描即將提交的變動，防止密鑰洩露與未經瑞亞審批之角色變更。

echo "🔍 正在檢查提交內容是否存在敏感資訊..."

# 檢查是否有 API Key 標籤 (Gemini: AIzaSy)
if git diff --cached | grep -qE "AIzaSy[A-Za-z0-9_-]{35}"; then
    echo "❌ 警告：檢測到 Gemini API Key 洩露！"
    echo "請移除代碼中的 Key，改用環境變數管理。"
    exit 1
fi

# 檢查是否有 Telegram Bot Token 格式
if git diff --cached | grep -qE "[0-9]{10}:[A-Za-z0-9_-]{35}"; then
    echo "❌ 警告：檢測到 Telegram Bot Token 洩露！"
    exit 1
fi

# 👑 檢查是否有角色註冊或 instance 異動
if git diff --cached --name-only | grep -qE "^(\.agent/roles/|scripts/rhea_role_steward\.py)"; then
    echo "👑 檢測到角色變更，正在驗證瑞亞神殿封印 (Rhea Seal Check)..."
    python3 scripts/rhea_role_steward.py --check || {
        echo "❌ [Pre-Commit Blocked] 角色變更未經瑞亞審批蓋印！請執行 python3 scripts/rhea_role_steward.py --seal 後再提交。"
        exit 1
    }
fi

echo "✅ 安全與角色守門檢查通過。"
exit 0
