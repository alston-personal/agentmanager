#!/bin/bash

# Antigravity Git Security Guard
# 此腳本會掃描即將提交的變動，防止密鑰洩露。

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

echo "✅ 安全檢查通過。"
exit 0
