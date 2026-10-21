"""Regression guard for exhausted #470 verification attempts."""
import importlib.util
from pathlib import Path
import unittest

MODULE = Path(__file__).resolve().parents[1] / "scripts" / "work_completion.py"
spec = importlib.util.spec_from_file_location("agentos_work_completion_retry", MODULE)
wc = importlib.util.module_from_spec(spec)
spec.loader.exec_module(wc)


class RetryAdmissionTests(unittest.TestCase):
    def test_historical_verification_count_is_rejected_in_any_state(self):
        for status in ("blocked", "waiting_external", "accepted", "in_progress"):
            with self.subTest(status=status):
                item = {"status": status, "last_blocker_kind": "VERIFICATION",
                        "machine_retry_count": 364, "blocker": None}
                self.assertFalse(wc.retry_admission_allowed(item))

    def test_prior_verification_failure_is_allowed_within_limit(self):
        self.assertTrue(wc.retry_admission_allowed({
            "status": "accepted", "last_blocker_kind": "VERIFICATION",
            "machine_retry_count": wc.VERIFICATION_RETRY_LIMIT - 1,
        }))

    def test_other_machine_failures_use_general_limit(self):
        for kind in ("PROVIDER_CAPACITY", "RUNTIME_HEALTH"):
            self.assertFalse(wc.retry_admission_allowed({
                "status": "waiting_external", "last_blocker_kind": kind,
                "machine_retry_count": wc.MACHINE_RETRY_BUDGET,
            }))

    def test_new_unblocked_work_is_not_impeded(self):
        self.assertTrue(wc.retry_admission_allowed({
            "status": "accepted", "machine_retry_count": 0,
        }))


if __name__ == "__main__":
    unittest.main()
