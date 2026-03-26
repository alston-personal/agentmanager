---
name: matters_publisher
description: 提供發送內容至 Matters.town 的核心能力，支援自動登入、草稿建立與文章發布。
---

# Matters Publisher Skill

## 🎯 目的
提供一個通用的介面，讓不同的 Agent 或專案能輕鬆地將內容發表至 Matters.town，解決 Token 過期與重複開發發布邏輯的問題。

## 🚀 功能
1. **自動登入**：透過 Email 與密碼自動獲取並更新 `__access_token`。
2. **草稿同步**：將 Markdown 內容轉換為 HTML 並上傳至 Matters 草稿箱。
3. **文章發布**：將現有草稿正式發布。
4. **進度追蹤**：支援循序發布（一章接一章）並記錄發度。

## 📋 使用方法

### 環境變數需求
- `MATTERS_EMAIL`: Matters 登入信箱。
- `MATTERS_PASSWORD`: Matters 登入密碼。
- `MATTERS_TOKEN`: (選填) 手動提供的 Token。

### 核心腳本說明
1. **`matters_bot.py`**: 封裝 GraphQL API 的核心類別。
2. **`publish_chapter.py`**: 通用的單章發布工具。

### 調用範例 (Python)
```python
from matters_publisher.matters_bot import MattersBot
bot = MattersBot(email="...", password="...")
draft_id = bot.create_draft("標題", "內容", "摘要")
```

## 🔧 整合至專案
在專案的 Workflow 或發布腳本中，應優先調用此 Skill 的腳本而非自行實作。
