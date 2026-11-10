import tempfile
import unittest
from pathlib import Path
from agent_core.control_plane import ControlPlaneStore
from agent_core.bounty_probe_executor import run_leased_probe

class BountyProbeExecutorTests(unittest.TestCase):
    def test_unleased_refused(self):
        with tempfile.TemporaryDirectory() as folder:
            store = ControlPlaneStore(Path(folder) / "control.sqlite3")
            task = store.submit_task("github.repo.read", {"repo":"a/b"}, "unleased")
            with self.assertRaises(ValueError):
                run_leased_probe(store, task, node_id="node-1")

    def test_other_node_refused(self):
        with tempfile.TemporaryDirectory() as folder:
            store = ControlPlaneStore(Path(folder) / "control.sqlite3")
            store.submit_task("github.repo.read", {"repo":"a/b"}, "owned")
            task = store.lease_next_task("node-1", ["github.repo.read"])
            with self.assertRaises(ValueError):
                run_leased_probe(store, task, node_id="node-2")

    def test_forged_status_refused(self):
        with tempfile.TemporaryDirectory() as folder:
            store = ControlPlaneStore(Path(folder) / "control.sqlite3")
            task = store.submit_task("github.repo.read", {"repo":"a/b"}, "forged")
            fake = dict(task, status="leased", targetNodeId="node-1", leaseUntil="2099-01-01T00:00:00Z")
            with self.assertRaises(ValueError):
                run_leased_probe(store, fake, node_id="node-1")

    def test_expired_lease_refused(self):
        with tempfile.TemporaryDirectory() as folder:
            store = ControlPlaneStore(Path(folder) / "control.sqlite3")
            store.submit_task("github.repo.read", {"repo":"a/b"}, "expired")
            task = store.lease_next_task("node-1", ["github.repo.read"], lease_seconds=-1)
            with self.assertRaises(ValueError):
                run_leased_probe(store, task, node_id="node-1")

    def test_write_capability_refused(self):
        with tempfile.TemporaryDirectory() as folder:
            store = ControlPlaneStore(Path(folder) / "control.sqlite3")
            store.submit_task("github.pr.write", {"repo":"a/b"}, "write")
            task = store.lease_next_task("node-1", ["github.pr.write"])
            with self.assertRaises(ValueError):
                run_leased_probe(store, task, node_id="node-1")

if __name__ == "__main__":
    unittest.main()
