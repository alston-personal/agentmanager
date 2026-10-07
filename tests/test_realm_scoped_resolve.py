import os
import tempfile
import threading
import unittest
from pathlib import Path

from agent_core.node_registry import NodeRegistry
from agent_core.realm_fabric import RealmFabricStore
from agent_core.realm_server import RealmHTTPServer
from agent_core.work_bindings import WorkBindingStore
from agentos_node.thin_client import ThinClientPolicy
from agentos_node.thin_client_transport import ThinClientTransport, build_client


class TestScopedRealmResolve(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.previous_data_root = os.environ.get("AGENT_DATA_ROOT")
        os.environ["AGENT_DATA_ROOT"] = str(self.root)

        registry = NodeRegistry(path=self.root / "nodes.json")
        self.fabric = RealmFabricStore(path=self.root / "realm" / "fabric.json", node_registry=registry)
        self.fabric.initialize_realm("realm-test")
        self.server = RealmHTTPServer(("127.0.0.1", 0), self.fabric)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base_url = f"http://127.0.0.1:{self.server.server_address[1]}"
        self.workspace = self.root / "workspace"
        self.workspace.mkdir()
        self.config_path = self.root / "client.json"

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)
        if self.previous_data_root is None:
            os.environ.pop("AGENT_DATA_ROOT", None)
        else:
            os.environ["AGENT_DATA_ROOT"] = self.previous_data_root
        self.tmp.cleanup()

    def _client(self, node_id: str):
        invite = self.fabric.create_invite(expires_minutes=5, label=node_id)
        policy = ThinClientPolicy(readable_roots=(self.workspace,))
        config = ThinClientTransport.enroll(
            one_url=self.base_url,
            invite_id=invite["invite_id"],
            code=invite["code"],
            node_id=node_id,
            policy=policy,
            config_path=self.config_path,
        )
        return build_client(config, policy)

    def test_bare_continue_resolves_local_executor_work(self):
        client = self._client("vopc5750")
        store = WorkBindingStore()
        store.upsert({
            "work_id": "work-oracle-newer",
            "node_id": "oracle",
            "executor_id": "shell",
            "participant_id": "codex",
            "state": "active",
        })
        store.upsert({
            "work_id": "work-vopc-gui",
            "node_id": "vopc5750",
            "executor_id": "gui-worker",
            "participant_id": "gemini-web",
            "state": "active",
        })

        result = client.resolve(
            executor_id="gui-worker",
            participant_id="gemini-web",
            session_id="brand-new-chat",
        )

        self.assertTrue(result["ok"])
        self.assertEqual(result["resolution"]["work_id"], "work-vopc-gui")
        self.assertEqual(result["resolution"]["source"], "participant_executor")
        self.assertTrue(result["availability"]["work_binding"])

    def test_bare_continue_does_not_guess_unrelated_work(self):
        client = self._client("dqa03backup")
        WorkBindingStore().upsert({
            "work_id": "work-oracle-only",
            "node_id": "oracle",
            "executor_id": "shell",
            "participant_id": "codex",
            "state": "active",
        })

        result = client.resolve(
            executor_id="shell",
            participant_id="codex",
            session_id="new-chat",
        )

        self.assertTrue(result["ok"])
        self.assertIsNone(result["resolution"]["work_id"])
        self.assertEqual(result["resolution"]["source"], "no_continuation")


if __name__ == "__main__":
    unittest.main()
