"""Execute the canonical Gateway deploy receipt validator against bounded fixtures.

The PR build-check never deploys; this tests the existing workflow's embedded
post-deploy validator without issuing ONE requests or touching Oracle.
"""
import json
import subprocess
import tempfile
import unittest
from pathlib import Path

SHA = "a" * 40
WORKFLOW = Path(".github/workflows/oracle-deploy-realm-gateway.yml")


def validation_program():
    text = WORKFLOW.read_text(encoding="utf-8")
    anchor = '          python3 - "$RECEIPT" "$GITHUB_SHA" <<' + "'PY'\n"
    code = text.split(anchor, 1)[1].split("\n          PY", 1)[0]
    return "\n".join(line[10:] if line.startswith("          ") else line for line in code.splitlines()) + "\n"


def fixture(stdout, ok=True, rc=0):
    return {
        "schema": "agentos.bootstrap-receipt/v1",
        "action": "agentos.realm_gateway.deploy",
        "executor_user": "ubuntu",
        "executor_uid": 1001,
        "source_commit": SHA,
        "ok": ok,
        "scheduler": {
            "node": "oracle", "worker_role": "maintenance",
            "worker_id": "oracle-maintenance", "locks": ["oracle-core-runtime"]
        },
        "steps": [{"step": "run_script", "returncode": rc, "stdout": stdout, "stderr": ""}]
    }


BG = "\n".join([
    "realm_gateway_dashboard_bg=PASS",
    "realm_gateway_dashboard_slot=green",
    "realm_gateway_dashboard_port=3041",
    "realm_core_runtime_staged=PASS",
    "realm_core_runtime_cutover=PASS",
    "realm_core_runtime_restart=PASS",
    "realm_core_runtime_source_commit=" + SHA,
    "realm_gateway_public=PASS",
    "realm_gateway_bootstrap_public=PASS",
    "realm_gateway_dispatch_public=PASS",
    "realm_gateway_source_commit=" + SHA,
    "realm_gateway_blue_green=PASS",
    "nginx_mutation=BLUE_GREEN_HELPER",
    "root_privilege=NGINX_RELOAD_ONLY",
])
LEGACY = "\n".join([
    "route_source=" + SHA + ":dashboard/app/api/agentos/[...path]/route.ts",
    "dashboard_build=PASS",
    "realm_gateway_bootstrap_local=PASS",
    "realm_gateway_bootstrap_public=PASS",
    "realm_gateway_source_commit=" + SHA,
    "realm_gateway_public=PASS",
    "nginx_mutation=NONE",
])


class GatewayReceiptContractTest(unittest.TestCase):
    def validate(self, receipt):
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / "receipt.json"
            path.write_text(json.dumps(receipt), encoding="utf-8")
            return subprocess.run(
                ["python3", "-", str(path), SHA],
                input=validation_program(),
                text=True, capture_output=True, check=False,
            )

    def test_blue_green_success(self):
        result = self.validate(fixture(BG))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("realm_gateway_release_mode=blue_green", result.stdout)

    def test_legacy_success(self):
        result = self.validate(fixture(LEGACY))
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_missing_blue_green_marker_fails(self):
        result = self.validate(fixture(BG.replace("realm_gateway_dispatch_public=PASS", "")))
        self.assertNotEqual(result.returncode, 0)

    def test_failed_oracle_receipt_never_accepted(self):
        self.assertNotEqual(self.validate(fixture(BG, ok=False)).returncode, 0)
        self.assertNotEqual(self.validate(fixture(BG, rc=1)).returncode, 0)

    def test_spoofed_legacy_fallback_denied(self):
        # Blue/Green started, but final acceptance marker is absent.
        result = self.validate(fixture(LEGACY + "\nrealm_gateway_dashboard_bg=PASS"))
        self.assertNotEqual(result.returncode, 0)


if __name__ == "__main__":
    unittest.main()
