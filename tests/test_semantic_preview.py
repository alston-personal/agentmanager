import unittest
from unittest import mock

from agentos_node import semantic_preview as semantic_preview_module


class FakeWorker:
    daemon = False

    def __init__(self):
        self.terminated = False
        self.killed = False

    def start(self):
        pass

    def is_alive(self):
        return not self.terminated and not self.killed

    def join(self, timeout=None):
        pass

    def terminate(self):
        self.terminated = True

    def kill(self):
        self.killed = True


class FakeQueue:
    def get(self, timeout=None):
        raise semantic_preview_module.queue.Empty


class FakeContext:
    def Queue(self):
        return FakeQueue()

    def Process(self, target=None, args=()):
        return FakeWorker()


class TestSemanticPreviewIsolation(unittest.TestCase):
    def test_worker_timeout_is_bounded(self):
        with mock.patch.object(semantic_preview_module, "_require_windows"), \
             mock.patch.object(semantic_preview_module.multiprocessing, "get_context", return_value=FakeContext()), \
             mock.patch.object(semantic_preview_module.time, "monotonic", side_effect=[0.0, 3.0]):
            with self.assertRaisesRegex(TimeoutError, "worker_start"):
                semantic_preview_module.semantic_preview({"timeout_seconds": 2})

    def test_worker_result_is_returned_with_isolation_metadata(self):
        result = {
            "schema": "agentos.desktop-semantic-preview/v0.1",
            "read_only": True,
            "mode": "foreground-window-only",
            "state_hash": "abc",
            "foreground": {},
            "preview": {},
        }

        class ResultQueue:
            def get(self, timeout=None):
                return {"kind": "result", "result": dict(result)}

        class ResultContext(FakeContext):
            def Queue(self):
                return ResultQueue()

        class FinishedWorker(FakeWorker):
            def is_alive(self):
                return False

        class FinishedContext(ResultContext):
            def Process(self, target=None, args=()):
                return FinishedWorker()

        with mock.patch.object(semantic_preview_module, "_require_windows"), \
             mock.patch.object(semantic_preview_module.multiprocessing, "get_context", return_value=FinishedContext()), \
             mock.patch.object(semantic_preview_module.time, "monotonic", side_effect=[0.0, 0.1, 0.2]):
            returned = semantic_preview_module.semantic_preview({"timeout_seconds": 2})

        self.assertTrue(returned["worker"]["isolated"])
        self.assertEqual(returned["worker"]["last_stage"], "worker_start")
        self.assertTrue(returned["read_only"])


if __name__ == "__main__":
    unittest.main()
