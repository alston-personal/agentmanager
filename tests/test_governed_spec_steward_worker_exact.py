from __future__ import annotations

import unittest
from unittest.mock import Mock, patch

from agentos_node.governed_spec_steward_worker import GovernedSpecStewardWakeWorker


class GovernedSpecStewardExactWakeTests(unittest.TestCase):
    def test_process_exact_pins_selected_candidate_for_kernel_call(self):
        candidate_a = (1, object(), {"wake_id": "wake-a", "presence_generation": 1})
        candidate_b = (2, object(), {"wake_id": "wake-b", "presence_generation": 2})
        fake_worker = Mock()
        fake_worker.runtime_root = "/tmp/runtime"
        fake_worker._capsules.return_value = [candidate_a, candidate_b]

        wrapper = GovernedSpecStewardWakeWorker.__new__(GovernedSpecStewardWakeWorker)
        wrapper.worker = fake_worker

        def process_one(*, now=None):
            selected = fake_worker._capsules()
            self.assertEqual(selected, [candidate_b])
            return "processed"

        fake_worker.process_one.side_effect = process_one
        with patch(
            "agentos_node.governed_spec_steward_worker.require_governed_spec_steward_delivery"
        ) as authority:
            result = wrapper.process_exact(wake_id="wake-b", presence_generation=2)

        self.assertEqual(result, "processed")
        authority.assert_called_once_with("/tmp/runtime", candidate_b[2])

    def test_process_exact_does_not_fall_back_to_other_wake(self):
        candidate = (1, object(), {"wake_id": "wake-a", "presence_generation": 1})
        fake_worker = Mock()
        fake_worker._capsules.return_value = [candidate]
        wrapper = GovernedSpecStewardWakeWorker.__new__(GovernedSpecStewardWakeWorker)
        wrapper.worker = fake_worker

        with patch(
            "agentos_node.governed_spec_steward_worker.require_governed_spec_steward_delivery"
        ) as authority:
            result = wrapper.process_exact(wake_id="wake-missing", presence_generation=9)

        self.assertIsNone(result)
        authority.assert_not_called()
        fake_worker.process_one.assert_not_called()


if __name__ == "__main__":
    unittest.main()
