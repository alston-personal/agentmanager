from __future__ import annotations

import unittest

from agentos_node.node_adapter import AdapterRegistry, load_configured_adapters
from agentos_node.wow_control_adapter import CAPABILITY, WoWControlAdapter


class WoWControlContractTests(unittest.TestCase):
    def test_off_by_default(self):
        self.assertEqual(load_configured_adapters(""), [])

    def test_opt_in_uses_existing_node_registry(self):
        adapters = load_configured_adapters("agentos_node.wow_control_adapter")
        registry = AdapterRegistry(adapters)
        self.assertEqual(registry.capabilities(), [CAPABILITY])
        self.assertEqual(registry.resolve(CAPABILITY).adapter_id, "wow-control")

    def test_unbound_reader_fail_closed(self):
        self.assertEqual(
            WoWControlAdapter().execute({"action": CAPABILITY}),
            {"status": "UNAVAILABLE", "reason": "RUNTIME_READER_NOT_BOUND"},
        )

    def test_rejects_command_and_extra_arguments(self):
        adapter = WoWControlAdapter(lambda: {"state": "READY"})
        for request in [
            {"action": "shell.exec"},
            {"action": CAPABILITY, "command": "whoami"},
            {"action": CAPABILITY, "allow": "Bash(*)"},
            {"action": CAPABILITY, "cwd": "C:\\secrets"},
        ]:
            with self.subTest(request=request), self.assertRaises(ValueError):
                adapter.execute(request)

    def test_read_only_reader(self):
        adapter = WoWControlAdapter(lambda: {"paw": "unknown", "receipt": None})
        self.assertEqual(
            adapter.execute({"action": CAPABILITY}),
            {"status": "OK", "snapshot": {"paw": "unknown", "receipt": None}},
        )


if __name__ == "__main__":
    unittest.main()
