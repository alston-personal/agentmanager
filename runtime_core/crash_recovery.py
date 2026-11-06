"""
runtime_core/crash_recovery.py
==============================
Crash Recovery Manager (接手與崩潰復原管理器)。
負責將 MSCS (Minimal Sufficient Cognitive State) 與 In-flight Partial Stream 打包，
並為接手 Agent (Successor Worker) 編譯零認知斷層的 Handover Prompt。
"""
from __future__ import annotations

import json
import os
import time
import uuid
from typing import Any, Dict, Optional

from .cognitive_state import (
    CanonicalReasoningState,
    CrashPack,
    PrunedPath,
    SemanticBreakpoint,
    TensionItem,
)
from .semantic_analyzer import SemanticBreakpointAnalyzer


class CrashRecoveryManager:
    """管理崩潰狀態捕獲、持久化與跨模型接手 Prompt 編譯。"""

    def __init__(self, data_root: str = "/home/ubuntu/agent-data"):
        self.data_root = data_root

    def assemble_crash_pack(
        self,
        *,
        last_committed_mscs: CanonicalReasoningState,
        in_flight_partial_stream: str,
        error: Exception | str,
        worker_id: str = "worker-01",
        semantic_breakpoint: Optional[SemanticBreakpoint] = None,
    ) -> CrashPack:
        """組裝 CrashPack 物件。"""
        crash_id = f"crash_{int(time.time())}_{uuid.uuid4().hex[:6]}"
        err_msg = str(error) if isinstance(error, Exception) else error

        if semantic_breakpoint is None:
            semantic_breakpoint = SemanticBreakpointAnalyzer.analyze(in_flight_partial_stream)

        # 粗估 token 數 (字元數 / 3)
        est_tokens = len(in_flight_partial_stream) // 3

        return CrashPack(
            crash_id=crash_id,
            worker_id=worker_id,
            failed_at=time.time(),
            error_summary=err_msg,
            last_committed_mscs=last_committed_mscs,
            in_flight_partial_stream=in_flight_partial_stream,
            semantic_breakpoint=semantic_breakpoint,
            token_count_estimate=est_tokens,
        )

    def compile_handover_prompt(
        self,
        crash_pack: CrashPack,
        *,
        token_budget: int = 4000,
    ) -> str:
        """
        編譯接手 Agent 的 Handover Prompt。
        保證包含：
          1. 系統角色切換聲明 (Successor Failover)
          2. Minimal Sufficient Cognitive State (MSCS - 包含 Constraints, Decisions, Pruned Paths, Tensions)
          3. 前一 Agent 崩潰前輸出的 In-flight Partial Stream
          4. 語意斷點提示 (Breakpoint Hint) 與接續指令
        """
        mscs = crash_pack.last_committed_mscs
        bp = crash_pack.semantic_breakpoint

        # 1. 構建 Constraints 列表
        constraints_str = ""
        for c in mscs.constraints:
            constraints_str += f"  - [{c.get('id', 'C')}]: {c.get('desc', '')}\n"

        # 2. 構建 Decisions 列表
        decisions_str = ""
        for d in mscs.decisions:
            decisions_str += f"  - [{d.get('id', 'D')}]: {d.get('desc', '')}\n"

        # 3. 構建 Pruned Paths (負空間 - 避免接手者重蹈覆轍)
        pruned_str = ""
        for p in mscs.pruned_paths:
            pruned_str += f"  - [{p.id}] 已排除路徑: {p.desc} (原因: {p.pruned_reason})\n"

        # 4. 構建 Tensions (未決張力)
        tensions_str = ""
        for t in mscs.tensions:
            tensions_str += f"  - [{t.id}] 未決張力: {t.desc}\n"

        # 5. 斷點指引
        breakpoint_guidance = (
            f"【斷點型態】: {bp.breakpoint_type.value}\n"
            f"【接續指引】: {bp.continuation_hint}"
        )
        if bp.unclosed_delimiter:
            breakpoint_guidance += f"\n【未閉合符號】: {bp.unclosed_delimiter}"

        # 6. 組裝完整 Prompt
        prompt = f"""# 🚨 AgentOS Live Failover Handover (無縫接手指令)

你目前作為【接手 Agent (Successor Worker)】接替因中途中斷崩潰的前任 Worker ({crash_pack.worker_id})。
請根據下方提供的 Minimal Sufficient Cognitive State (MSCS) 與前任 Worker 崩潰前留下的未完成串流，
**零認知斷層地直接接續輸出**，切勿重複已產出的內容或破壞語意流。

---

## 1. 認知狀態 (MSCS v{mscs.ir_version})
- **主要目標**: [{mscs.primary_goal_id}] {mscs.primary_goal_desc}
- **核心約束 (Constraints)**:
{constraints_str or '  (無特殊約束)'}
- **已確立決策 (Decisions)**:
{decisions_str or '  (無已定決策)'}
- **排除路徑 (Pruned Paths - 嚴禁重複嘗試)**:
{pruned_str or '  (無排除路徑)'}
- **未決張力 (Tensions)**:
{tensions_str or '  (無未決張力)'}
- **當前推進邊界 (Frontier Task)**: {mscs.frontier_task}
- **核心待解問題**: {mscs.frontier_question}
- **推論方向**: {mscs.frontier_direction}

---

## 2. 崩潰現場與語意斷點
{breakpoint_guidance}

---

## 3. 前任 Worker 崩潰前輸出的 In-flight Partial Stream:
<<<IN_FLIGHT_STREAM_START>>>
{crash_pack.in_flight_partial_stream}
<<<IN_FLIGHT_STREAM_END>>>

---

## 4. 接手執行指令
請從上述 `<<<IN_FLIGHT_STREAM_END>>>` 緊接的語意斷點處**直接開始輸出後續內容**。
保持語氣、程式碼結構與推論邏輯的高度連貫性。
"""
        return prompt.strip()

    def persist_crash_pack(
        self,
        crash_pack: CrashPack,
        project_id: str = "agentmanager",
    ) -> str:
        """
        持久化 CrashPack 至 Data Layer。
        遵守 AgentOS 規範：寫入 /home/ubuntu/agent-data/projects/{project}/memory/crash_packs/
        """
        data_dir = os.path.join(self.data_root, "projects", project_id, "memory", "crash_packs")
        try:
            os.makedirs(data_dir, exist_ok=True)
        except OSError:
            # Fallback 到本地目錄
            data_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "crash_packs")
            os.makedirs(data_dir, exist_ok=True)

        file_path = os.path.join(data_dir, f"{crash_pack.crash_id}.json")
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(crash_pack.to_json(indent=2))

        return file_path
