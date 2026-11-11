# Stop 寫回與必經 IR 驗證器的相容性

狀態：source candidate，未部署。沿用 #2189／#2215 的 `agentos_node/ir_stop_sync.py`，不新增角色或背景模型。

## 自動與明確變更分開

- `handle_stop_payload` 強制使用 `automatic=True`。最後一輪的使用者／模型文字只形成 `turn-checkpoint` evidence，標示 `RECORDED` 和 `task_relevance=NOT_EVALUATED`，不推定完成或相關性。
- 自動路徑保留既有 goal、constraints、decisions、pending_tasks、capability、continuation 與認知欄位；即使原 continuation 只有 recommended_action，也保持完整形狀。執行狀態沿用原值，不把已完成工作改回 in_progress。
- `advance_active_ir_checkpoint` 的明確 next_action／decision／completed_tasks 必須提供 observed project/index/IR；錯代即拒絕、不重試到新世代。沒有明確變更的 checkpoint 也不會把摘要升格成決策。
- 找不到有效 active selector 時拒絕寫入，不自行猜測 Core。自動路徑遇到衝突不跨世代重試。
- 所有發布仍經同一個 `publish_project_continuation` 驗證器。hook 錯誤不阻塞聊天結束，但會寫入資料層的失敗 audit，只有錯誤類型、不包含可能敏感的例外文字。

## 測試與部署限制

`tests/test_ir_stop_evidence.py` 使用真正的暫存 canonical publisher／selector／resolver，驗證算術 probe 不改語義、驗證 receipt、明確更新的 generation fence、selector 缺失與錯誤 audit。

此變更補足 [IR_VALIDATION.md](IR_VALIDATION.md) 記錄的舊 Stop 相容性缺口；部署時須同時帶入 publisher、validator、handoff writer、Stop module，並確保 MCP adapter 能傳遞 observed generation 欄位。不能只更新其中一個檔案，也不能把單元測試當作已完成各平台部署。

正式 active IR 中既有的錯誤 next_action 未在此變更中修復。全域 selector 與會話／work-item 尚無可信綁定，故 unrelated evidence 仍可能被記錄；本修正保證的是已知自動路徑不再把該回覆升格成任務語義。語義相關性判斷與已受污染世代的受控修復仍待處理。
