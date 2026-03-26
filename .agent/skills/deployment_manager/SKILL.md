---
name: deployment_manager
description: 統一管理伺服器部署邏輯，支援 Nginx 反向代理、PM2 進程管理與 SSL 證書自動化。
---

# Deployment Manager Skill

## 🎯 目的
將雜亂的部署步驟（Nginx, PM2, SSL, Build）封裝成標準化工具，減少 AI Agent 在執行部署任務時的手動錯誤。

## 🚀 功能
1. **環境偵測**：自動判斷專案類型（Next.js, Vite, Node...）。
2. **設定檔生成**：自動產生符合標準的 Nginx 與 PM2 設定。
3. **流程自動化**：一鍵執行 Build、Migrate 與 Service Reload。
4. **健康檢查**：部署後自動驗證服務是否穩定。

## 🔧 核心腳本 (scripts/)
- `deploy_core.py`: 主引擎，負責接收參數並調用子模組。
- `config_builder.py`: 負責產生 Nginx 與 PM2 配置。
- `env_checker.py`: 驗證相關依賴（Node, Nginx...）。

## 📋 使用方法
在 Workflow 中調用：
```bash
python3 .agent/skills/deployment_manager/scripts/deploy_core.py --project <name> --domain <domain>
```
