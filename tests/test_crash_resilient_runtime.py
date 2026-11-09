"""
tests/test_crash_resilient_runtime.py
=====================================
驗證 AgentOS Crash-Resilient Cognitive Runtime 核心功能：
1. Streaming Interceptor & Buffer
2. 語意斷點識別 (Semantic Breakpoint Analyzer)
3. MSCS 認知狀態與 Crash Pack 組裝 (CrashRecoveryManager)
4. 接手 Prompt 編譯 (Handover Prompt Compiler)
5. 模擬崩潰與自動 Failover (End-to-End Resiliency)
"""
import unittest
import os
import shutil
import tempfile
from runtime_core.cognitive_state import (
    BreakpointType,
    CanonicalReasoningState,
    CrashPack,
    PrunedPath,
    TensionItem,
)
from runtime_core.semantic_analyzer import SemanticBreakpointAnalyzer
from runtime_core.streaming_interceptor import StreamingInterceptor
from runtime_core.crash_recovery import CrashRecoveryManager


class TestStreamingInterceptor(unittest.TestCase):
    """測試串流攔截器與 In-flight 緩衝區機制。"""

    def test_streaming_interceptor_normal(self):
        chunks = ["Hello", " ", "AgentOS", " ", "World!"]
        collected = []

        def on_chunk(c):
            collected.append(c)

        interceptor = StreamingInterceptor(
            iter(chunks),
            worker_id="test-worker-01",
            on_chunk=on_chunk,
        )

        output = list(interceptor.iterate())
        self.assertEqual(output, chunks)
        self.assertEqual(collected, chunks)
        self.assertEqual(interceptor.full_text, "Hello AgentOS World!")
        self.assertFalse(interceptor.is_interrupted)
        self.assertIsNotNone(interceptor.completed_at)

    def test_streaming_interceptor_crash_capture(self):
        def faulty_stream():
            yield "Starting step 1: analysis..."
            yield "\nStarting step 2: generating code..."
            raise ConnectionResetError("Remote API dropped connection suddenly!")

        crashed_partial = []
        crashed_error = []

        def on_crash(partial_text, err, bp):
            crashed_partial.append(partial_text)
            crashed_error.append(err)

        interceptor = StreamingInterceptor(
            faulty_stream(),
            worker_id="worker-crash-test",
            on_crash=on_crash,
        )

        with self.assertRaises(ConnectionResetError):
            for _ in interceptor.iterate():
                pass

        self.assertTrue(interceptor.is_interrupted)
        self.assertIn("Starting step 2: generating code...", interceptor.full_text)
        self.assertEqual(len(crashed_partial), 1)
        self.assertIn("generating code...", crashed_partial[0])
        self.assertIsInstance(crashed_error[0], ConnectionResetError)
        self.assertIsNotNone(interceptor.breakpoint)


class TestSemanticBreakpointAnalyzer(unittest.TestCase):
    """測試語意斷點分析器。"""

    def test_unclosed_code_block(self):
        partial_code = (
            "Here is the implementation:\n"
            "```python\n"
            "def handle_stream():\n"
            "    buffer = []\n"
        )
        bp = SemanticBreakpointAnalyzer.analyze(partial_code)
        self.assertEqual(bp.breakpoint_type, BreakpointType.UNCLOSED_CODE_BLOCK)
        self.assertEqual(bp.unclosed_delimiter, "```python")
        self.assertIn("未閉合的程式碼區塊", bp.continuation_hint)

    def test_unclosed_json(self):
        partial_json = (
            'Call tool with arguments:\n'
            '{"action": "deploy_service", "params": {"target": "oracle-vm", "dry_run": false'
        )
        bp = SemanticBreakpointAnalyzer.analyze(partial_json)
        self.assertEqual(bp.breakpoint_type, BreakpointType.UNCLOSED_JSON)
        self.assertEqual(bp.unclosed_delimiter, "{")
        self.assertIn("未閉合的結構化資料", bp.continuation_hint)

    def test_mid_reasoning_step(self):
        partial_step = (
            "1. 檢查當前記憶層狀態\n"
            "2. 建立 StreamingInterceptor 代理\n"
            "3. 實作語意斷點分析器以確保"
        )
        bp = SemanticBreakpointAnalyzer.analyze(partial_step)
        self.assertEqual(bp.breakpoint_type, BreakpointType.MID_REASONING_STEP)
        self.assertEqual(bp.unclosed_delimiter, "3.")
        self.assertIn("斷在推論步驟", bp.continuation_hint)

    def test_partial_sentence(self):
        partial_sentence = "AgentOS 是針對多代理系統設計的"
        bp = SemanticBreakpointAnalyzer.analyze(partial_sentence)
        self.assertEqual(bp.breakpoint_type, BreakpointType.PARTIAL_SENTENCE)
        self.assertIn("斷在句子中間", bp.continuation_hint)

    def test_clean_end(self):
        clean_text = "所有單元測試已順利完成。\n"
        bp = SemanticBreakpointAnalyzer.analyze(clean_text)
        self.assertEqual(bp.breakpoint_type, BreakpointType.CLEAN)


class TestCrashRecoveryManager(unittest.TestCase):
    """測試 Crash Pack 組裝、Prompt 編譯與持久化。"""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.recovery_mgr = CrashRecoveryManager(data_root=self.temp_dir)

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_assemble_and_compile_handover_prompt(self):
        mscs = CanonicalReasoningState(
            ir_version="0.2.2",
            project_id="agentmanager",
            primary_goal_id="G1",
            primary_goal_desc="建立 AgentOS Crash-Resilient Cognitive Runtime",
            constraints=[
                {"id": "C1", "desc": "Working Agent 絕不負責自身的權威狀態持久化。"},
                {"id": "C2", "desc": "接手 Context 必須同時包含 Last Committed MSCS 與 In-flight Partial Stream。"},
            ],
            decisions=[
                {"id": "D1", "desc": "採 Sidecar / Shadow Extractor 異步解析生成 State Delta。"},
            ],
            pruned_paths=[
                PrunedPath(id="P1", desc="同步阻塞式 State Extraction", pruned_reason="大幅增加 TTFT 首字延遲"),
            ],
            tensions=[
                TensionItem(id="T1", desc="Token-level 即時攔截粒度與異步解析開銷的權衡"),
            ],
            frontier_task="T_IMPL_01: 實作 AgentOS Middleware Proxy",
            frontier_question="如何從 Partial Stream 精確標記語意斷點？",
            frontier_direction="以 Middleware 攔截 Stream 流，崩潰時注入 MSCS 組裝 Prompt",
        )

        in_flight_stream = (
            "我們正在實作 Crash Recovery 機制。\n"
            "```python\n"
            "class CrashRecoveryManager:\n"
            "    def __init__(self):\n"
        )

        pack = self.recovery_mgr.assemble_crash_pack(
            last_committed_mscs=mscs,
            in_flight_partial_stream=in_flight_stream,
            error=ConnectionResetError("Socket timeout"),
            worker_id="gemini-worker-01",
        )

        self.assertEqual(pack.worker_id, "gemini-worker-01")
        self.assertEqual(pack.semantic_breakpoint.breakpoint_type, BreakpointType.UNCLOSED_CODE_BLOCK)

        # 編譯 Handover Prompt
        prompt = self.recovery_mgr.compile_handover_prompt(pack)

        self.assertIn("🚨 AgentOS Live Failover Handover", prompt)
        self.assertIn("G1", prompt)
        self.assertIn("建立 AgentOS Crash-Resilient Cognitive Runtime", prompt)
        self.assertIn("C1", prompt)
        self.assertIn("D1", prompt)
        self.assertIn("P1", prompt)
        self.assertIn("大幅增加 TTFT 首字延遲", prompt)
        self.assertIn("T1", prompt)
        self.assertIn("<<<IN_FLIGHT_STREAM_START>>>", prompt)
        self.assertIn("class CrashRecoveryManager:", prompt)
        self.assertIn("<<<IN_FLIGHT_STREAM_END>>>", prompt)

        # 測試持久化
        saved_file = self.recovery_mgr.persist_crash_pack(pack, project_id="test_proj")
        self.assertTrue(os.path.exists(saved_file))
        self.assertIn("test_proj", saved_file)


if __name__ == "__main__":
    unittest.main()
