"""Hermes must be advertised by the existing Oracle Employee Wake Node."""
import unittest
from unittest.mock import patch

from agentos_node.employee_wake_node import EMPLOYEE_IDS, _bind_presences


class HermesWakePresenceTests(unittest.TestCase):
    def test_hermes_in_same_canonical_wake_roster(self):
        self.assertIn("hermes-technology-scout", EMPLOYEE_IDS)
        self.assertEqual(len(EMPLOYEE_IDS), len(set(EMPLOYEE_IDS)))
        self.assertIn("the-paw", EMPLOYEE_IDS)

    def test_one_presence_bind_per_registered_employee(self):
        class FakePresence:
            def __init__(self, runtime, registry):
                self.calls = []
            def get(self, employee_id):
                return None
            def bind(self, employee_id, node_id, presence_id, **kwargs):
                self.calls.append((employee_id, node_id, presence_id, kwargs))
        with patch("agentos_node.employee_wake_node.EmployeePresenceRegistry", FakePresence):
            bound = _bind_presences(runtime=object(), registry=object(),
                                    node_id="oracle-employee-wake-node",
                                    presence_id="test-presence")
        self.assertEqual([row[0] for row in bound.calls], list(EMPLOYEE_IDS))
        self.assertTrue(all(row[1] == "oracle-employee-wake-node"
                            and row[2] == "test-presence"
                            and row[3].get("ttl_seconds") == 120
                            for row in bound.calls))


if __name__ == "__main__":
    unittest.main()
