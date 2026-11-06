"""
runtime_core/streaming_interceptor.py
=====================================
AgentOS 非阻塞 Streaming Interceptor & In-flight Buffer。
攔截 LLM 串流，零 TTFT 延遲損耗，並在發生中斷或異常時自動捕獲 In-flight 狀態。
"""
from __future__ import annotations

import time
from typing import Any, Callable, Generator, Iterable, List, Optional
from .cognitive_state import SemanticBreakpoint
from .semantic_analyzer import SemanticBreakpointAnalyzer


class StreamingInterceptor:
    """
    Middleware Streaming Interceptor。
    作為 Worker 與呼叫端之間的透明代理層。
    """

    def __init__(
        self,
        stream_source: Iterable[str],
        *,
        worker_id: str = "worker-01",
        on_chunk: Optional[Callable[[str], None]] = None,
        on_crash: Optional[Callable[[str, Exception, SemanticBreakpoint], None]] = None,
        on_complete: Optional[Callable[[str], None]] = None,
    ):
        self.stream_source = stream_source
        self.worker_id = worker_id
        self.on_chunk = on_chunk
        self.on_crash = on_crash
        self.on_complete = on_complete

        # In-flight Buffer
        self.chunks: List[str] = []
        self.started_at: float = time.time()
        self.completed_at: Optional[float] = None
        self.is_interrupted: bool = False
        self.error: Optional[Exception] = None
        self.breakpoint: Optional[SemanticBreakpoint] = None

    @property
    def full_text(self) -> str:
        """取得當前已累積的所有文字。"""
        return "".join(self.chunks)

    def iterate(self) -> Generator[str, None, None]:
        """
        以 Generator 形式透傳串流 Chunk，同時即時記錄至 In-flight Buffer。
        若上游中斷、超時或發生異常，將自動觸發 Crash 攔截並封裝語意斷點。
        """
        self.started_at = time.time()
        try:
            for chunk in self.stream_source:
                if chunk:
                    self.chunks.append(chunk)
                    if self.on_chunk:
                        try:
                            self.on_chunk(chunk)
                        except Exception:
                            pass
                    yield chunk
            
            # 正常完成
            self.completed_at = time.time()
            self.breakpoint = SemanticBreakpointAnalyzer.analyze(self.full_text)
            if self.on_complete:
                self.on_complete(self.full_text)

        except (Exception, GeneratorExit) as e:
            # 捕獲異常或中斷
            self.is_interrupted = True
            self.completed_at = time.time()
            if isinstance(e, GeneratorExit):
                self.error = ConnectionResetError("Stream client disconnected prematurely (GeneratorExit)")
            else:
                self.error = e

            # 立即分析斷點
            self.breakpoint = SemanticBreakpointAnalyzer.analyze(self.full_text)

            if self.on_crash:
                try:
                    self.on_crash(self.full_text, self.error, self.breakpoint)
                except Exception:
                    pass

            if not isinstance(e, GeneratorExit):
                raise e
