from __future__ import annotations

import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SERVICE = ROOT / ".agent" / "scripts" / "agentos-core-supervisor.service"
ENV_EXAMPLE = ROOT / ".agent" / "scripts" / "agentos-core-supervisor.env.example"
DOC = ROOT / "docs" / "CORE_SUPERVISOR.md"


class CoreSupervisorAssetTests(unittest.TestCase):
    def test_service_runs_observe_plan_daemon_with_network_disabled(self):
        text = SERVICE.read_text(encoding="utf-8")
        self.assertIn("ExecStart=/usr/bin/python3 -m agent_core.core_supervisor_daemon", text)
        self.assertIn("PrivateNetwork=true", text)
        self.assertIn("NoNewPrivileges=true", text)
        self.assertIn("ProtectSystem=strict", text)
        self.assertIn("ReadWritePaths=/home/ubuntu/agent-data/employee-runtime", text)
        lowered = text.casefold()
        self.assertNotIn("workflow_dispatch", lowered)
        self.assertNotIn("github actions", lowered)
        self.assertNotIn("shell.exec", lowered)

    def test_environment_example_is_non_secret_configuration_only(self):
        text = ENV_EXAMPLE.read_text(encoding="utf-8")
        self.assertIn("AGENTOS_EMPLOYEE_RUNTIME_ROOT=", text)
        self.assertIn("AGENTOS_SUPERVISOR_LEADER_LEASE_SECONDS=", text)
        lowered = text.casefold()
        for forbidden in ("password=", "token=", "secret=", "authorization=", "bearer "):
            self.assertNotIn(forbidden, lowered)

    def test_docs_keep_source_merge_separate_from_live_deployment(self):
        text = DOC.read_text(encoding="utf-8")
        self.assertIn("Repository merge != Oracle deployment != operating acceptance", text)
        self.assertIn("event != authority", text)
        self.assertIn("PrivateNetwork=true", text)
        self.assertRegex(text, re.compile(r"S4.*governed ONE wake delivery", re.IGNORECASE))


if __name__ == "__main__":
    unittest.main()
