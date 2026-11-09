#!/bin/bash

# Antigravity Git Security & Governance Guard
# 此腳本會掃描即將提交的變動，防止密鑰洩露、未經瑞亞審批之角色變更、以及代碼與說明文件脫節。

echo "🔍 正在檢查提交內容是否存在敏感資訊..."

# 1. 檢查是否有 API Key 標籤 (Gemini: AIzaSy)
if git diff --cached | grep -qE "AIzaSy[A-Za-z0-9_-]{35}"; then
    echo "❌ 警告：檢測到 Gemini API Key 洩露！"
    echo "請移除代碼中的 Key，改用環境變數管理。"
    exit 1
fi

# 2. 檢查是否有 Telegram Bot Token 格式
if git diff --cached | grep -qE "[0-9]{10}:[A-Za-z0-9_-]{35}"; then
    echo "❌ 警告：檢測到 Telegram Bot Token 洩露！"
    exit 1
fi

# 3. 👑 檢查是否有角色註冊或 instance 異動
if git diff --cached --name-only | grep -qE "^(\.agent/roles/|scripts/rhea_role_steward\.py)"; then
    echo "👑 檢測到角色變更，正在驗證瑞亞神殿封印 (Rhea Seal Check)..."
    python3 scripts/rhea_role_steward.py --check || {
        echo "❌ [Pre-Commit Blocked] 角色變更未經瑞亞審批蓋印！請執行 python3 scripts/rhea_role_steward.py --seal 後再提交。"
        exit 1
    }
fi

# 4. 📚 檢查說明文件與代碼同步狀態 (Documentation Reality Guard - 第二道提交門禁)
echo "📚 正在檢查說明文件與代碼同步狀態 (Documentation Reality Guard)..."
python3 scripts/documentation_reality_guard.py --staged || {
    echo "❌ [Pre-Commit Blocked] 提交前必須確保說明文件反映代碼最新狀態！請在同一 commit 內更新 README.md, docs/CURRENT_STATE.md, AGENTS.md 或 ONBOARDING.md。"
    exit 1
}

echo "✅ 安全、角色封印與文件同步檢查全面通過。"
exit 0
