"""Guard the existing main-only Action Runtime rollout against accidental bypass."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github/workflows/main-action-runtime-migration-20261007.yml"

class MainRuntimeDeployRoutingTests(unittest.TestCase):
    def test_existing_main_runner_window_carrier_tracks_relevant_providers(self):
        body = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("branches: [main]", body)
        for path in (
            "agent_core/executor_job_contract.py",
            "agentos_node/deployment_inspect_provider.py",
            "agentos_node/executor_job_action_relay.py",
            "agentos_node/executor_job_adapter.py",
            "agentos_node/action_relay.py",
        ):
            self.assertIn(f"- '{path}'", body)
        self.assertIn("agentos.runtime", body)
        self.assertIn('"operation":"repair"', body)
        self.assertIn("runner_window", body.lower())
        self.assertIn("action_relay_install=PASS", body)
        self.assertIn("agentos_source_commit=", body)
        self.assertIn("oracle-action-runtime-rollout", body)
        self.assertIn("cancel-in-progress: false", body)

    def test_preflight_and_no_bypass(self):
        body = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("needs: [validate]", body)
        self.assertIn("tests.test_deployment_inspect_one", body)
        self.assertIn("tests.test_deployment_capability", body)
        self.assertNotIn("runs-on: [self-hosted", body)
        self.assertNotIn("StrictHostKeyChecking=accept-new", body)
        self.assertNotIn("ssh ", body)
        self.assertNotIn("git push", body)
        self.assertIn("id-token: write", body)

if __name__ == "__main__":
    unittest.main()
