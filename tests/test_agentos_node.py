from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from agent_core.governance_directory import seed_core
from scripts.agentos_node import harvest


class AgentOSNodeTests(unittest.TestCase):
    def test_harvest_advertises_governance_and_resource_capabilities(self):
        ids = {item["id"] for item in harvest()["capabilities"]}
        self.assertIn("governance.resolve", ids)
        self.assertIn("resource.query", ids)
        self.assertIn("resource.verify.site", ids)

    def test_directory_resolves_existing_port_manager_contract(self):
        with tempfile.TemporaryDirectory() as td:
            directory = Path(td) / "governance" / "directory.json"
            seed_core(directory)
            data = json.loads(directory.read_text(encoding="utf-8"))
            manager = data["entities"]["manager://port"]
            self.assertIs(manager["authority"]["exclusive"], True)
            self.assertIn("capability://network.port.allocate", manager["owns"])


if __name__ == "__main__":
    unittest.main()
