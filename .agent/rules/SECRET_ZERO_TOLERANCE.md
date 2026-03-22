# 🔐 憲法：Secret 管理零容忍法則 (Secret Zero-Tolerance Policy)
# 來源：2026-03-22 API Key 外洩事故
# 嚴重性：CRITICAL — 違反者視為最高失職

## 🔴 事故根因分析 (Root Cause Analysis)

**日期**: 2026-03-22  
**事件**: Agent 在開發 `fortune_server.py` 時，將 `GEMINI_API_KEY` 直接硬碼寫入原始碼，並立即執行 `git push` 上傳至公開 GitHub。Google 自動安全掃描在幾分鐘內偵測並鎖死該 Key，導致整個 AI 算命後端功能完全中斷。

**根本原因**：
1. Agent 為求「快速開發」，跳過了 Secret 安全層的基礎核查。
2. 沒有在 `git add` 前進行「敏感資料掃描」。
3. 過度自信「這樣讀取就夠了」的誤判，沒有使用現有的 `.env` 架構。

---

## 🚫 絕對禁止行為 (Absolute Forbidden Actions)

> 以下行為，任何 Agent 在任何情況下均不得執行，無例外：

1. **禁止在任何原始碼檔案中直接撰寫任何 Secret 值**
   - API Keys、Tokens、Passwords、Connection Strings 全部禁止
   - 包含但不限於：`GEMINI_API_KEY`, `GITHUB_TOKEN`, `TELEGRAM_BOT_TOKEN`

2. **禁止執行 `git commit` 前不掃描 staged 檔案**
   - 每次 commit 前必須用 `git diff --cached` 確認沒有任何已知 secret 格式

3. **禁止把 `.env` 加入 `git add`**
   - `.env` 必須永遠在 `.gitignore` 裡面

---

## ✅ 強制執行標準 (Mandatory Standards)

### Secret 讀取的唯一合法方式：
```python
# ✅ 正確：從環境變數讀取
import os
API_KEY = os.environ.get("GEMINI_API_KEY")
if not API_KEY:
    raise RuntimeError("Secret not found. Check .env or environment.")

# ✅ 可接受的 fallback（僅限本機開發）：從 .env 檔案讀取
# 但此 .env 路徑本身永遠不得被 git 追蹤

# ❌ 絕對禁止
API_KEY = "AIzaSyXXXXXXXXXXXXX"  # 不論是否為自己的 key，一律禁止
```

### 在任何 Commit 前的強制檢查清單：
```bash
# 1. 確認 .gitignore 正確覆蓋所有 secret 檔案
grep -r "\.env" .gitignore

# 2. 掃描即將提交的 diff 中是否有 key 格式
git diff --cached | grep -iE "(api_key|token|secret|password)\s*=\s*['\"][a-zA-Z0-9_\-]{10,}"
```

---

## 🏛️ 憲法修訂記錄

| 版本 | 日期 | 原因 |
|------|------|------|
| v1.0 | 2026-03-22 | 因 GEMINI_API_KEY 外洩事故，首次立法 |
