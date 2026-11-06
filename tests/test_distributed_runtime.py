import unittest

from runtime_core.canonical_ir import CanonicalIR
from runtime_core.remote_runtime import RemoteRuntimeWorker


class TestDistributedRuntime(unittest.TestCase):
    def test_canonical_ir_roundtrip_and_digest(self):
        ir = CanonicalIR(
            goal="continue implementation",
            project_id="agentmanager",
            capability="agentos.ir.validate",
            payload={"step": 1},
        )
        restored = CanonicalIR.from_json(ir.to_json())
        self.assertEqual(restored.to_dict(), ir.to_dict())
        self.assertEqual(restored.digest(), ir.digest())

    def test_remote_runtime_emits_lineage_continuation(self):
        worker = RemoteRuntimeWorker("test-worker")
        worker.register("agentos.ir.validate", lambda ir: {"ok": True})
        ir = CanonicalIR(
            goal="continue implementation",
            project_id="agentmanager",
            capability="agentos.ir.validate",
        )
        result = worker.execute(ir)
        self.assertEqual(result.status, "succeeded")
        self.assertIsNotNone(result.continuation_ir)
        self.assertEqual(result.continuation_ir.parent_ir_id, ir.ir_id)
        self.assertTrue(result.continuation_ir.continuation["ready_for_next_agent"])

    def test_unregistered_capability_is_rejected(self):
        worker = RemoteRuntimeWorker("test-worker")
        ir = CanonicalIR(
            goal="do not execute arbitrary commands",
            project_id="agentmanager",
            capability="shell.exec",
        )
        result = worker.execute(ir)
        self.assertEqual(result.status, "rejected")
        self.assertEqual(result.result["error"], "unsupported_capability")


if __name__ == "__main__":
    unittest.main()
