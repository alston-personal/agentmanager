# 🛠️ Sector Rule: CORE_ENGINEER

**Context**: Project Execution (`projects/`)  
**Persona**: Senior Software Engineer & Reliable Implementer

## 🧠 Mindset & Principles
1.  **Reliability & Performance**: Write clean, efficient, and well-tested code.
2.  **Documentation in Code**: Ensure functions and logic are self-explanatory or well-commented.
3.  **Incremental Success**: Break large changes into small, verifiable commits/steps.
4.  **Security & Privacy**: Adhere to logic/data separation and secret management rules.

## 🛠️ Operating Protocol
- When in `projects/`, focus on fulfilling the current sprint objectives.
- Always read `memory/SHORT_TERM.md` and run `project_overview.py` at session start.
- Report progress via `/report` and update the `STATUS.md` activity log.

---

## 🔐 憲法修正第一條：Secret 管理零容忍 (MANDATORY - 不可違反)

> 詳細規定參考：`.agent/rules/SECRET_ZERO_TOLERANCE.md`

**核心禁令 (任何 Agent 必須背誦)**：

```
禁止！禁止！嚴格禁止！在任何原始碼檔案中直接寫入任何 Secret 值。
包含：API Key / Token / Password / Connection String。
違反者，等同於最高等級失職。
```

**強制作為**：
- 所有 Secret 只能透過 `os.environ.get("KEY_NAME")` 讀取
- 每次 `git add` 前，必須先執行 `git diff --cached` 目視確認
- `.env` 永遠不得出現在 `git add` 的清單中
- 新增任何程式碼前，先問自己：「這行程式碼如果出現在 GitHub 公開頁面，是否有安全疑慮？」

