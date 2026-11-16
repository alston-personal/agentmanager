# Canonical IR 必經驗證腳本

狀態：source candidate，尚未部署。範圍：Core 的 `publish_project_continuation`；不是所有 persona／transport／Effective IR 的通用驗證器。不新增角色或模型呼叫。

## 規則與執行入口

`agent_core/ir_validation.py` 的 `RULE_VERSION = core-continuation/1` 定義可執行規則。寫入器在持有既有世代鎖、確認 CAS 與父代之後，建立暫存輸出之前，直接呼叫它。失敗會拒絕寫入正式 head／continuation；通過的發布 receipt 附上規則版本與父子內容雜湊。

規則涵蓋必要欄位與型別、父子世代、禁止靜默移除父代欄位，以及已知 Stop 自動寫回不得改動 goal／constraints／decisions／pending_tasks／capability／continuation／認知欄位。自動 Stop 可記錄 evidence，但不能把最後一段對話提升成下一步，也不能建立正式初始 IR。

手動預檢使用同一套邏輯，讀取 canonical_ir 物件（不是外層 envelope）：

```bash
python3 scripts/validate_canonical_ir.py candidate.json --parent parent.json
python3 scripts/validate_canonical_ir.py candidate.json --parent parent.json --writer ir_stop_sync
python3 -m unittest tests.test_ir_validation
```

預檢通過不授予發布權；真正寫入仍重新驗證、檢查 governance identity 與 CAS。失敗 exit code 為 1；輸出不包含輸入內容。不存在「模型說已檢查」就可跳過的參數。

## 規則變更也必須受檢查

`scripts/documentation_reality_guard.py` 已接入既有 pre-commit／CI，強制下列契約檔案在同一變更集同步更新：驗證器、CLI、`tests/test_ir_validation.py`、本文件。這是同步變更檢查，不是語義正確性的證明；新增或改變規則時應更新 RULE_VERSION、加入通過／拒絕案例並審查預期差異。現有 CI 會執行驗證器測試。

規則、腳本與測試應在同一個可審查的變更中提交，不先部署新規則再補測試；正式部署仍受現有發布權限管制。

## 已知限制與相容性

- 現有舊 Stop hook 會同時改 decisions 與 next_action；部署此 gate 後這種更新會被拒絕。部署前需將 hook 改為 evidence-only 或另設具明確授權與 session/work-item 綁定的提交路徑。此變更未部署，也未悄悄修復正式 IR。
- `writer` 來自現有發布 metadata，並非簽章身分。此 gate 限制已知自動寫回路徑，不能防止有直接檔案寫入權者繞過，或惡意呼叫者偽裝 explicit。OS 權限與可信 session 綁定仍屬另行整合工作。
- 腳本不理解任意文字是否偏題，receipt 明確標示 `semantic_relevance=NOT_EVALUATED`。算術污染案例是以禁止自動寫回改任務語義來攔截，沒有關鍵字黑名單。
- 欄位存在不保證其內容充分，也不代表跨模型認知連續性已被證明。人工／模型語義審查可補充，但不能取代此必經檢查。
