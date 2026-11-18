import unittest

from scripts.issue_completion_reconciliation import reconcile


def entry(status, *, passed=False, evidence=None):
    return {"status": status, "verification": {"status": "passed" if passed else "pending"},
            "evidence": [] if evidence is None else evidence}


class IssueCompletionReconciliationTests(unittest.TestCase):
    def run_case(self, issue_state, work_status, *, passed=False, evidence=None):
        return reconcile([{"number": 2297, "state": issue_state}], {
            "items": {"gh-issue-2297-engineering":
                      entry(work_status, passed=passed, evidence=evidence)}
        })["findings"][0]

    def test_closed_accepted_is_anomaly(self):
        self.assertEqual(self.run_case("closed", "accepted")["code"],
                         "CLOSED_WITHOUT_VERIFIED_DONE")

    def test_closed_blocked_is_anomaly(self):
        self.assertEqual(self.run_case("closed", "blocked")["code"],
                         "CLOSED_WITHOUT_VERIFIED_DONE")

    def test_closed_verifying_is_anomaly(self):
        self.assertEqual(self.run_case("closed", "verifying")["code"],
                         "CLOSED_WITHOUT_VERIFIED_DONE")

    def test_verified_done_closed_is_ok(self):
        self.assertEqual(self.run_case("closed", "done", passed=True, evidence=["receipt"])["code"],
                         "VERIFIED_CLOSED")

    def test_closed_done_without_receipt_is_anomaly(self):
        self.assertEqual(self.run_case("closed", "done", passed=True)["code"],
                         "CLOSED_WITHOUT_VERIFIED_DONE")

    def test_cancelled_requires_review_not_forced_reopening(self):
        self.assertEqual(self.run_case("closed", "cancelled")["code"],
                         "CLOSED_CANCELLED_REVIEW_REASON")

    def test_open_issue_not_misclassified(self):
        self.assertEqual(self.run_case("open", "blocked")["code"],
                         "NO_CLOSURE_ANOMALY")

    def test_missing_issue_not_assumed_closed(self):
        data = reconcile([], {"items": {"gh-issue-2297-engineering": entry("blocked")}})
        self.assertEqual(data["findings"], [])

    def test_conflicting_snapshots_fail_closed(self):
        with self.assertRaisesRegex(ValueError, "conflicting_issue_states"):
            reconcile([{"number": 2297, "state": "open"},
                       {"number": 2297, "state": "closed"}], {"items": {}})

    def test_determinism_and_no_mutation(self):
        import copy
        issues = [{"number": 2297, "state": "closed"}]
        state = {"items": {"gh-issue-2297-engineering": entry("blocked")}}
        before = copy.deepcopy((issues, state))
        self.assertEqual(reconcile(issues, state), reconcile(issues, state))
        self.assertEqual((issues, state), before)


if __name__ == "__main__":
    unittest.main()
