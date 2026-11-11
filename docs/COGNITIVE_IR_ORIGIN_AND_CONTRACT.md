# IR 原意、寫作契約與偏移盤點

狀態：歷史與程式盤點已完成；下述統一語義契約與遷移方案為 **proposed**，不是已部署 schema。
Owner：AgentOS Core 維護者。Target：AgentOS Core、ONE continuation、executor context adapters。
盤點基準：`85ea65e4563d4c69a432ac6232c1a0a7446a3c3d`（2026-11-11）。

## 1. 可以追溯的原意與證據界線

IR = Intermediate Representation（中介表示）。AgentOS 的方向是把足以接續工作的狀態外部化，讓更換模型、會話或機器後，仍可接住原有目標、判斷與工作位置。它不是單純的聊天摘要或待辦清單，也不代表搬移模型隱藏狀態。

本次找到的是可追溯的程式、設計文件與 issue，**沒有找到最初提出概念的完整使用者對話**。因此下表是目前可證實的演進，不宣稱第一筆提交就是構想誕生時間；程式註解中的版本號也不能作為年代證據。

| 時間／證據 | 當時可確認的內容 | 限制 |
|---|---|---|
| 2026-08-21，[bae8e0b3](https://github.com/alston-personal/agentmanager/commit/bae8e0b3e52dea98d149c79c8e688dc619258a24) | `CanonicalIR` 將 goal、constraints、context、artifacts、decisions、pending_tasks、continuation 與父代關係放入與主機無關的 JSON 交接表示 | 是傳輸／續行契約，不是一般認知充分性證明 |
| 2026-08-26，[cceb2b79](https://github.com/alston-personal/agentmanager/commit/cceb2b79c23f9679c0207d9ee7f1445686ca1d56) | 公開架構明確追問「另一個模型接續所需的最小表示」，把 Cognitive IR 與任意模型切換保留為研究 | 不能把工程切片成功改寫成研究目標已完成 |
| 2026-08-28，`7debb106` 引入 [Core Control Room](CORE_CONTROL_ROOM.md#6-memory-continuation-state-and-cognitive-ir) | 記憶與 canonical state 經 retrieve/reconcile/compile 產生 continuation IR，再交給 adapter；要求保留 rejected paths、open questions、next direction | IR 不是第四層記憶，也不應另立衝突的事實來源 |
| 2026-09-01，[bootstrap 校正](issue-152-ir-bootstrap-note.md) | 新會話從 ONE 選定的 project/index/IR 接續，工作目錄不能選擇任務 | 解決選擇與注入問題，不代表語義完整 |
| 2026-10-08，[#1683](https://github.com/alston-personal/agentmanager/issues/1683) | 提出分層 Effective IR：來源、版本、範圍、繼承與衝突解析；明確分離 context visibility 與 execution authority | issue 的設計與驗收條件不是部署證據 |
| 2026-11-06，`fe1ecf98` 納入 [cognitive_state.py](../runtime_core/cognitive_state.py) | `CanonicalReasoningState` 自稱 MSCS／IR v0.2.2，具備 pruned_paths、tensions、frontier；Crash Pack 區分 committed state 與未完成串流 | 此檔案可查 git 引入時間為 11-06；註解不能證明構想始於該日，更不能證明 ONE 已完整接線 |

**原意的工作定義：保存足以讓接手者知道「正在解決什麼、為何走到這裡、哪些方向已排除、還不知道什麼、下一步怎麼驗證」的可追溯工作狀態。**

## 2. IR、規則與推理的責任

- 憲法／治理來源定義權限與限制；執行守衛在作用邊界檢查，不能只依賴模型讀過文字。
- Effective IR 可以表示適用規則及其來源、範圍、版本與解析結果。繼承規則文字不等於取得操作權限。
- continuation／cognitive IR 表示本次工作的目標、證據、決策與未解問題；引用治理結果，不複製成另一份可自行改寫的憲法。
- agent rules 與 adapter 保留接入、選擇、投影、工具使用和寫回協定；任務狀態不應分散在多份啟動提示中。
- 模型依據這些資訊產生判斷。IR 保存可檢驗的決策理由與假設，不要求逐字保存隱藏思維鏈，也不保證下一模型產生相同內部推理。

新版使用者意圖優先於舊任務快照；證據更新可能使舊判斷失效。二者都不能悄悄覆蓋權限來源。真正的授權變更仍需有效的授權事件。

## 3. 寫作契約：最少應包含的語義（proposed）

這是作者與審查者使用的語義清單，**不是可直接提交給目前 `one_checkpoint` 的 JSON schema**。未知就寫「未知」並列驗證方向；不適用就說明原因，不能編造內容填欄位。

| 語義 | 應寫內容 | 不足的寫法 |
|---|---|---|
| 身分與世代 | project、scope、schema/profile、IR／parent／index、來源版本 | 只有檔名或「最新」 |
| 使用者意圖與目標 | 使用者要達成的結果、來源、最新修正、完成條件 | 「繼續處理」 |
| 適用限制與授權 | 規則來源／版本、有效範圍、可做與待核准的動作 | 把「工具可用」寫成「已授權」 |
| 已知事實與證據 | 主張、來源／receipt、時間與適用環境；區分觀察與推論 | 把模型說「完成」當作驗證 |
| 決策與理由 | 選了什麼、原因、依據、取捨、何時重新評估 | 只保留最終結論 |
| 排除路徑 | 曾否決的方案、理由／證據、重新考慮的條件 | 接手後重新嘗試同一失敗，或永久禁止合理重試 |
| 未解問題與矛盾 | 未驗證假設、衝突證據、風險、資訊缺口 | 把未知壓成確定結論 |
| 工作前沿 frontier | 當前任務、具體待解問題、下一個驗證方向 | 只寫下一個 shell 指令 |
| 任務生命週期 | 穩定 task ID、狀態、依賴、完成證據、阻塞原因 | 摘要寫完成但 pending 永遠不變 |
| 下一步與停止條件 | 已授權的下一個有效動作、驗收方式、真正需人介入之處 | 每做一項都要求使用者再說繼續 |
| 交接與壓縮資訊 | 提交世代、未完成動作、來源指標、保留／省略的內容與原因 | 靜默裁掉仍有效的決策，或把部分串流當作 committed state |

## 4. 可直接使用的寫作模板與例子

在正式 schema 遷移之前，可用以下 Markdown 作為設計稿或有版本的資料層交接附件。不要擅自新增目前 publisher 不接受的參數，也不要讓附件成為另一個 active selector。

```markdown
身分／來源世代：<project, scope, IR/index/parent, source refs>
目標與完成條件：<使用者要的結果；怎樣才算達成>
最新意圖／修正：<來源；哪些舊假設已失效>
限制／授權：<適用規則版本；仍需核准的作用>
事實與證據：<觀察、來源、環境、時間；推論另標>
決策：<選擇 → 理由 → 證據 → 重新評估條件>
排除路徑：<方案 → 排除原因 → 可重開條件>
未解問題／矛盾：<未知或競爭假設；如何區分>
Frontier：<active_task / active_question / reasoning_direction>
任務：<ID、狀態、依賴、完成證據或阻塞>
下一步／驗收：<已授權動作；預期證據>
壓縮／交接：<保留的語義；省略內容的來源；未完成動作>
```

例：排查 Claude 提早停止時，不只寫「修規則」。應記錄：「目標為已授權工作能持續推進；已觀察本機 bootstrap 有每輪只做一項限制；Windows 實際載入規則未知；先採修正序列續行規則；暫不採增加代理，因使用者限制 token；下一問題是 Windows 是否載入同版規則；以設定來源與實際行為驗證。」

這些是決策摘要，不需要保留整段對話。原文、長測試輸出與歷史放在既有資料來源，IR 保留足以追溯的引用。若必須縮短，先移除重複敘述；仍有效的限制、決策理由、未解問題與完成狀態不可因排序較舊而無聲消失。

## 5. 已觀察到的實作落差

1. **同名 schema，不同資料形狀。** [CanonicalIR](../runtime_core/canonical_ir.py) 的 `agentos.ir/v1` 使用結構化 decisions／pending_tasks、context／artifacts 與 project_id；[ONE handoff writer](../agent_core/canonical_ir_handoff.py) 使用字串清單，project_id 在外層，另加 index_id／evidence。不能僅憑相同 schema 字串宣稱可無損互換。
2. **認知欄位與 ONE 路徑未統一。** MSCS 有 pruned_paths、tensions、frontier；ONE writer 沒有專用欄位或對應映射。資訊可能被人寫進文字，但沒有完整性保證。
3. **重建子代可能丟掉擴充欄位。** `advance_canonical_ir` 以固定欄位重新建立 canonical_ir；即使父代含有 context／artifacts／frontier，也沒有自動保留路徑。這是程式可見的遺失風險，不代表已證實某筆生產資料遭刪除。
4. **解析器不代表嚴格語義驗證。** `CanonicalIR.from_dict` 過濾未知欄位，且 dataclass 型別標註不會驗證每個巢狀值。成功解析不能證明理由、未解問題或任務狀態保留。
5. **有界化與語義保存需一起驗收。** [#2189](https://github.com/alston-personal/agentmanager/pull/2189) 的 rolling history／Stop sync 與 [#2215](https://github.com/alston-personal/agentmanager/pull/2215) 的明確任務完成修正，屬另行審查的變更；後者不會補齊前述認知欄位，也不證明所有舊決策都能安全裁切。

## 6. 防偏移與遷移驗收（proposed，尚未實裝）

沿用既有 IR、publisher、治理與 context adapter，不新增第二套記憶或控制平面。以下工作需另立實作變更，本文不宣稱完成：

- [ ] 定義具名 profile／版本與明確映射，分清 transport IR、reasoning state、canonical continuation、effective governance；避免繼續共用名稱卻改變欄位意義。
- [ ] 讓 publisher／adapter 對必要語義提供 preserve-or-reject：能保留就保留，不能保留就拒絕或明確回報遺失，禁止靜默吞欄位。
- [ ] 加入 round-trip fixture，驗證目標、限制、決策理由、排除路徑、未解問題、frontier 與任務狀態經寫回／壓縮／再注入後仍可恢復。
- [ ] 加入 stale generation、最新使用者修正、規則來源與授權邊界測試；明確完成待辦不得被 Stop 摘要重新建立。
- [ ] 設計跨模型接手基準：對照完整上下文、普通摘要、IR 三組，在相同任務與工具條件下，量測正確續行、重複探索、遺失限制、額外 token 與延遲；保存版本與失敗案例。
- [ ] 只有有代表性且可重複的結果，才能提升 Cognitive IR 成熟度；資料結構測試、MCP 連通或單次成功都不足以宣稱零成本任意模型切換。

變更審查應問：此變更會讓接手模型更知道「為何在這裡」，還是只剩「下一項要做什麼」？若刪除語義，必須記錄取捨與遷移方式；若只是改名或加提示文字，不得宣稱已有執行層防偏移保障。
