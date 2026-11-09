from __future__ import annotations

import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SERVICE = ROOT / ".agent" / "scripts" / "agentos-core-supervisor.service"
DELIVERY_DROPIN = ROOT / ".agent" / "scripts" / "agentos-core-supervisor-delivery.conf.example"
ENV_EXAMPLE = ROOT / ".agent" / "scripts" / "agentos-core-supervisor.env.example"
DELIVERY_POLICY = ROOT / "governance" / "core-supervisor-delivery.json"
DOC = ROOT / "docs" / "CORE_SUPERVISOR.md"


class CoreSupervisorAssetTests(unittest.TestCase):
    def test_base_service_remains_s3_sandbox_with_network_disabled(self):
        text = SERVICE.read_text(encoding="utf-8")
        self.assertIn("ExecStart=/usr/bin/python3 -m agent_core.core_supervisor_daemon", text)
        self.assertIn("PrivateNetwork=true", text)
        self.assertIn("NoNewPrivileges=true", text)
        self.assertIn("ProtectSystem=strict", text)
        self.assertIn("ReadWritePaths=/home/ubuntu/agent-data/employee-runtime", text)
        self.assertNotIn("ReadWritePaths=/home/ubuntu/agent-data/realm", text)
        lowered = text.casefold()
        self.assertNotIn("workflow_dispatch", lowered)
        self.assertNotIn("github actions", lowered)
        self.assertNotIn("shell.exec", lowered)

    def test_environment_example_defaults_delivery_to_disabled_and_contains_no_secret(self):
        text = ENV_EXAMPLE.read_text(encoding="utf-8")
        self.assertIn("AGENTOS_EMPLOYEE_RUNTIME_ROOT=", text)
        self.assertIn("AGENTOS_SUPERVISOR_LEADER_LEASE_SECONDS=", text)
        self.assertRegex(text, re.compile(r"^AGENTOS_SUPERVISOR_DELIVERY_MODE=disabled$", re.MULTILINE))
        self.assertIn("# AGENTOS_SUPERVISOR_DELIVERY_MODE=one_direct", text)
        self.assertIn("# AGENTOS_SUPERVISOR_ONE_DATA_ROOT=", text)
        lowered = text.casefold()
        for forbidden in ("password=", "token=", "secret=", "authorization=", "bearer "):
            self.assertNotIn(forbidden, lowered)

    def test_s4_dropin_is_explicit_narrow_filesystem_extension_only(self):
        text = DELIVERY_DROPIN.read_text(encoding="utf-8")
        self.assertIn("[Service]", text)
        self.assertIn("ReadWritePaths=/home/ubuntu/agent-data/realm", text)
        lowered = text.casefold()
        self.assertNotIn("privatenetwork=false", lowered)
        self.assertNotIn("execstart=", lowered)
        self.assertNotIn("environment=", lowered)
        self.assertNotIn("shell.exec", lowered)
        self.assertNotIn("github actions", lowered)

    def test_s4_policy_allows_only_exact_wake_through_one_direct(self):
        text = DELIVERY_POLICY.read_text(encoding="utf-8")
        self.assertIn('"capability": "agent.employee.wake.deliver"', text)
        self.assertIn('"allowed_transports": [', text)
        self.assertIn('"one_direct"', text)
        self.assertNotIn('"github_actions"', text)
        self.assertIn('"assignment_claim_authority": false', text)
        self.assertIn('"executor_selection_authority": false', text)
        self.assertIn('"credential_authority": false', text)

    def test_docs_keep_source_merge_separate_from_live_deployment(self):
        text = DOC.read_text(encoding="utf-8")
        self.assertIn("Repository merge != Oracle deployment != operating acceptance", text)
        self.assertIn("event != authority", text)
        self.assertIn("PrivateNetwork=true", text)
        self.assertIn("AGENTOS_SUPERVISOR_DELIVERY_MODE=disabled", text)
        self.assertIn("No shadow ONE", text)
        self.assertIn("awaiting_claim", text)
        self.assertRegex(text, re.compile(r"S4.*governed", re.IGNORECASE))
        self.assertIn("Neither marker may be claimed from source merge or static CI alone", text)


if __name__ == "__main__":
    unittest.main()
