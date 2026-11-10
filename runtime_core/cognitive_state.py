"""
runtime_core/cognitive_state.py
===============================
AgentOS Canonical Reasoning State (IR v0.2.2) 資料結構與定義。
專門支援跨模型認知連續性 (Cross-Model Cognitive Continuity) 與崩潰復原。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional
import json
import time


class BreakpointType(str, Enum):
    CLEAN = "CLEAN"                                # 正常結束，無斷裂
    UNCLOSED_CODE_BLOCK = "UNCLOSED_CODE_BLOCK"    # 斷在 Markdown 程式碼區塊內 (如 ```python ...)
    UNCLOSED_JSON = "UNCLOSED_JSON"                # 斷在 JSON / Tool Call 結構中
    MID_REASONING_STEP = "MID_REASONING_STEP"      # 斷在列點推論步驟中間 (如 1. ... 2. ...)
    PARTIAL_SENTENCE = "PARTIAL_SENTENCE"          # 斷在單句中間
    UNKNOWN = "UNKNOWN"                            # 未知斷裂型態


@dataclass
class SemanticBreakpoint:
    """描述 In-flight 串流中途斷裂時的語意邊界。"""
    breakpoint_type: BreakpointType
    last_complete_token_idx: int
    unclosed_delimiter: Optional[str] = None  # 如 "```python", "{", "["
    continuation_hint: str = ""              # 給接手 Agent 的修補接續引導
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "breakpoint_type": self.breakpoint_type.value,
            "last_complete_token_idx": self.last_complete_token_idx,
            "unclosed_delimiter": self.unclosed_delimiter,
            "continuation_hint": self.continuation_hint,
            "metadata": self.metadata,
        }


@dataclass
class PrunedPath:
    """決策負空間：已被排除的路徑與排除理由。"""
    id: str
    desc: str
    pruned_reason: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "type": "PRUNED_PATH",
            "desc": self.desc,
            "pruned_reason": self.pruned_reason,
        }


@dataclass
class TensionItem:
    """未決張力：尚未完全解決的架構矛盾或權衡。"""
    id: str
    desc: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "type": "TENSION",
            "desc": self.desc,
        }


@dataclass
class CanonicalReasoningState:
    """
    Minimal Sufficient Cognitive State (MSCS) — 符合 IR v0.2.2 規範。
    保存執行目標、硬性約束、已定決策、負空間 (Pruned Paths) 與未決張力 (Tensions)。
    """
    ir_version: str = "0.2.2"
    project_id: str = "agentmanager"
    primary_goal_id: str = "G1"
    primary_goal_desc: str = ""
    constraints: List[Dict[str, str]] = field(default_factory=list)
    decisions: List[Dict[str, str]] = field(default_factory=list)
    pruned_paths: List[PrunedPath] = field(default_factory=list)
    tensions: List[TensionItem] = field(default_factory=list)
    frontier_task: str = ""
    frontier_question: str = ""
    frontier_direction: str = ""
    timestamp: float = field(default_factory=time.time)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "ir_version": self.ir_version,
            "project_id": self.project_id,
            "timestamp": self.timestamp,
            "primary_goal": {
                "id": self.primary_goal_id,
                "desc": self.primary_goal_desc,
            },
            "constraints": self.constraints,
            "decisions": self.decisions,
            "pruned_paths": [p.to_dict() for p in self.pruned_paths],
            "tensions": [t.to_dict() for t in self.tensions],
            "frontier": {
                "active_task": self.frontier_task,
                "active_question": self.frontier_question,
                "reasoning_direction": self.frontier_direction,
            },
            "metadata": self.metadata,
        }

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=indent)


@dataclass
class CrashPack:
    """
    崩潰接手包 (Crash Pack)。
    由 Proxy / Middleware 在 Worker 崩潰時組裝，提供接手 Agent (Successor) 零認知斷層恢復。
    """
    crash_id: str
    worker_id: str
    failed_at: float
    error_summary: str
    last_committed_mscs: CanonicalReasoningState
    in_flight_partial_stream: str
    semantic_breakpoint: SemanticBreakpoint
    token_count_estimate: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "crash_id": self.crash_id,
            "worker_id": self.worker_id,
            "failed_at": self.failed_at,
            "error_summary": self.error_summary,
            "last_committed_mscs": self.last_committed_mscs.to_dict(),
            "in_flight_partial_stream": self.in_flight_partial_stream,
            "semantic_breakpoint": self.semantic_breakpoint.to_dict(),
            "token_count_estimate": self.token_count_estimate,
            "metadata": self.metadata,
        }

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=indent)
