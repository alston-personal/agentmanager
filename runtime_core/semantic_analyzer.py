"""
runtime_core/semantic_analyzer.py
=================================
分析 In-flight 殘留串流，精確標記語意斷點 (Semantic Breakpoint)，
為接手 Agent 提供零認知斷層的修補接續指引。
"""
from __future__ import annotations

import re
from typing import Optional
from .cognitive_state import BreakpointType, SemanticBreakpoint


class SemanticBreakpointAnalyzer:
    """分析中途中斷的 Stream 文字並產出 SemanticBreakpoint 描述。"""

    # 偵測 Markdown 程式碼區塊標記 (``` 或 ~~~)
    CODE_BLOCK_PATTERN = re.compile(r"(```[a-zA-Z0-9_-]*|~~~[a-zA-Z0-9_-]*)")
    
    # 偵測列表推論步驟 (如 1. , 2. , - [ ] 等)
    STEP_PATTERN = re.compile(r"(?:^|\n)\s*(\d+\.|\-|\*|\d+\))\s+([^\n]*)$")

    # 結尾標點符號 (完整句子判定)
    SENTENCE_ENDINGS = (".", "!", "?", "。", "！", "？", "\n", "```", "}")

    @classmethod
    def analyze(cls, partial_stream: str) -> SemanticBreakpoint:
        """
        針對給定的 partial_stream 進行靜態語意分析，識別斷點型態與修補建議。
        """
        if not partial_stream or not partial_stream.strip():
            return SemanticBreakpoint(
                breakpoint_type=BreakpointType.CLEAN,
                last_complete_token_idx=0,
                continuation_hint="Stream is empty. Successor should start reasoning from frontier goal.",
            )

        text = partial_stream

        # 1. 檢查是否有未閉合的 Markdown Code Block
        code_matches = list(cls.CODE_BLOCK_PATTERN.finditer(text))
        if len(code_matches) % 2 == 1:
            # 奇數個 code block 標記 -> 必定斷在程式碼區塊內
            last_open_match = code_matches[-1]
            delimiter = last_open_match.group(1)
            hint = (
                f"斷在未閉合的程式碼區塊 ({delimiter}) 內。"
                f"接手 Agent 請直接接續未寫完的程式碼，並在完成後正常使用 ``` 閉合。"
            )
            return SemanticBreakpoint(
                breakpoint_type=BreakpointType.UNCLOSED_CODE_BLOCK,
                last_complete_token_idx=len(text),
                unclosed_delimiter=delimiter,
                continuation_hint=hint,
                metadata={"code_block_start_idx": last_open_match.start()},
            )

        # 2. 檢查是否有未閉合的 JSON / Tool Call 結構 (例如 { 或 [ 未平衡)
        json_breakpoint = cls._check_unclosed_json(text)
        if json_breakpoint:
            return json_breakpoint

        # 3. 檢查是否斷在列點推論步驟中間 (Step in progress)
        step_match = cls.STEP_PATTERN.search(text)
        if step_match:
            step_prefix = step_match.group(1)
            partial_item = step_match.group(2)
            # 如果步驟內容最後沒有句號或換行，視為推論步驟中斷
            if partial_item and not partial_item.endswith(cls.SENTENCE_ENDINGS):
                hint = (
                    f"斷在推論步驟 '{step_prefix} {partial_item}' 中途。"
                    f"接手 Agent 請從當前步驟後半段接續思考，或補全此步驟後繼續下一步。"
                )
                return SemanticBreakpoint(
                    breakpoint_type=BreakpointType.MID_REASONING_STEP,
                    last_complete_token_idx=len(text),
                    unclosed_delimiter=step_prefix,
                    continuation_hint=hint,
                    metadata={"step_prefix": step_prefix, "partial_item": partial_item},
                )

        # 4. 檢查是否斷在句子中間 (Partial Sentence)
        stripped = text.rstrip()
        if not any(stripped.endswith(end) for end in cls.SENTENCE_ENDINGS):
            hint = "斷在句子中間。接手 Agent 請直接銜接最後一個未完成詞彙/子句，保持語意流暢。"
            return SemanticBreakpoint(
                breakpoint_type=BreakpointType.PARTIAL_SENTENCE,
                last_complete_token_idx=len(text),
                continuation_hint=hint,
            )

        # 5. 乾淨結尾或自然段落
        return SemanticBreakpoint(
            breakpoint_type=BreakpointType.CLEAN,
            last_complete_token_idx=len(text),
            continuation_hint="串流在語意完整處中斷。接手 Agent 可直接開始下一推論或回應階段。",
        )

    @classmethod
    def _check_unclosed_json(cls, text: str) -> Optional[SemanticBreakpoint]:
        """簡單括號計數器，檢查末尾是否處於未閉合的 JSON 結構中。"""
        # 從最後一個可能出現 JSON 的區域開始檢查
        last_brace = text.rfind("{")
        last_bracket = text.rfind("[")
        start_pos = max(last_brace, last_bracket)
        
        if start_pos == -1:
            return None

        # 計算從 start_pos 之後的括號平衡
        open_curly = 0
        open_square = 0
        in_string = False
        escape = False

        for char in text[start_pos:]:
            if escape:
                escape = False
                continue
            if char == "\\":
                escape = True
                continue
            if char == '"':
                in_string = not in_string
                continue
            if not in_string:
                if char == "{":
                    open_curly += 1
                elif char == "}":
                    open_curly -= 1
                elif char == "[":
                    open_square += 1
                elif char == "]":
                    open_square -= 1

        if open_curly > 0 or open_square > 0 or in_string:
            delim = "{" if open_curly > 0 else ("[" if open_square > 0 else '"')
            hint = (
                f"斷在未閉合的結構化資料 ({delim}) 內。"
                f"接手 Agent 請修復並補全 JSON/Tool-Call 引數，確保語法有效性。"
            )
            return SemanticBreakpoint(
                breakpoint_type=BreakpointType.UNCLOSED_JSON,
                last_complete_token_idx=len(text),
                unclosed_delimiter=delim,
                continuation_hint=hint,
                metadata={"open_curly": open_curly, "open_square": open_square, "in_string": in_string},
            )

        return None
