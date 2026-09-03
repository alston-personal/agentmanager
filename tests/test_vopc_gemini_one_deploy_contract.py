import json
import os
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from agentos_node import bootstrap_control


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "deploy_realm_fabric_candidate_user.sh"
WORKFLOW = ROOT / ".github" / "workflows" / "vopc5750-gemini-one-client-deploy.yml"


class VopcGeminiOneDeployContractTests(unittest.TestCase):
    def test_realm_fabric_action_is_fixed_and_exact_generation_only(self):
        self.assertIn(bootstrap_control.ACTION_DEPLOY_REALM_FABRIC, bootstrap_control.ALLOWED_ACTIONS)
        with patch.object(bootstrap_control, "_run_canonical_script") as run:
            bootstrap_control._execute(bootstrap_control.ACTION_DEPLOY_REALM_FABRIC, "a" * 40)
        run.assert_called_once_with(
            "scripts/deploy_realm_fabric_candidate_user.sh",
            timeout=180,
            source_commit="a" * 40,
        )

    def test_realm_fabric_request_requires_source_commit(self):
        with tempfile.TemporaryDirectory() as td:
            request_id = "realm-fabric-test"
            path = Path(td) / f"{request_id}.request.json"
            payload = {
                "schema": bootstrap_control.SCHEMA,
                "request_id": request_id,
                "action": bootstrap_control.ACTION_DEPLOY_REALM_FABRIC,
                "params": {},
                "created_at": datetime.now(timezone.utc).isoformat(),
                "authority": {
                    "source": "github-actions",
                    "target_user": "ubuntu",
                    "arbitrary_shell": False,
                },
            }
            path.write_text(json.dumps(payload), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "requires exact source_commit"):
                bootstrap_control._validate_request(path, payload)

    def test_candidate_script_has_identity_generation_route_and_rollback_fences(self):
        text = SCRIPT.read_text(encoding="utf-8")
        self.assertIn('if [ "$(id -un)" != "ubuntu" ]', text)
        self.assertIn('^[0-9a-f]{40}$', text)
        self.assertIn('git -C "$REPO" archive "$SOURCE_COMMIT" agent_core', text)
        self.assertIn('realm_fabric_candidate_rollback=COMPLETED', text)
        self.assertIn("ExecStart=/usr/bin/sg agentos", text)
        self.assertIn("-d '{\"selection\":\"active\"}'", text)
        self.assertIn('test "$PROBE_CODE" = 401', text)
        self.assertIn('realm_fabric_active_resolve_route=PASS', text)
        self.assertNotIn("pip install", text)

    def test_workflow_uses_typed_bootstrap_not_runner_user_systemd(self):
        text = WORKFLOW.read_text(encoding="utf-8")
        server = text.split("deploy-one-server:", 1)[1].split("deploy-vopc-client:", 1)[0]
        self.assertIn("'action':'agentos.realm_fabric.deploy'", server.replace(" ", ""))
        self.assertIn("'target_user':'ubuntu'", server.replace(" ", ""))
        self.assertIn("'arbitrary_shell':False", server.replace(" ", ""))
        self.assertIn("executor_user", server)
        self.assertIn("realm_fabric_candidate_deploy=PASS", server)
        self.assertNotIn("systemctl --user", server)
        self.assertNotIn("pip install", server)


if __name__ == "__main__":
    unittest.main()
