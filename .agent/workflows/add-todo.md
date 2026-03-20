---
description: 快速將新任務新增至指定專案或發想的 STATUS.md 中
---

# 📝 Add-Todo 工作流：新增任務 SOP

當您需要為特定專案新增代辦事項時，請務必使用此工作流。

## 🚀 執行步驟

1. **呼叫腳本**：
   使用 `scripts/add_todo.py` 指令。
   
   ```bash
   ./scripts/add_todo.py [專案名稱/Slug] "[任務描述]"
   ```

2. **驗證更新**：
   腳本會自動尋找 `agent-data` 中的 `STATUS.md` 並在 `## 📅 Todo List` 下方插入任務。

3. **同步全域**：
   任務新增後，建議執行 `./scripts/maintenance.py` 以更新 `GLOBAL_TODO_LIST.md`。

---
*遵循 Rule 0：任何任務新增應優先使用此工具而非手動編輯。*
