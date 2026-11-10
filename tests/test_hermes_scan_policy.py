import unittest
from datetime import datetime, timedelta, timezone
from agent_core.hermes_scan_policy import ScanSignals, propose_scan, plan_after_completed_scan

NOW = datetime(2026, 11, 7, 12, tzinfo=timezone.utc)

class HermesScanPolicyTests(unittest.TestCase):
    def test_first_scan_due_without_history(self):
        p = propose_scan(now=NOW, last_scan_at=None, signals=ScanSignals())
        self.assertTrue(p.should_run)
        self.assertEqual(p.interval_hours, 24)

    def test_quiet_backoff(self):
        for count, expected in [(0,24),(3,72),(7,168)]:
            p = propose_scan(now=NOW, last_scan_at=NOW, signals=ScanSignals(consecutive_empty_scans=count))
            self.assertEqual(p.interval_hours, expected)
            self.assertFalse(p.should_run)

    def test_critical_gap_is_bounded(self):
        s=ScanSignals(unresolved_critical_blocker=True)
        self.assertEqual(propose_scan(now=NOW,last_scan_at=NOW,signals=s).interval_hours,3)

    def test_upstream_event_is_not_unlimited(self):
        s=ScanSignals(external_event=True)
        self.assertEqual(propose_scan(now=NOW,last_scan_at=NOW,signals=s).interval_hours,1)
        self.assertFalse(propose_scan(now=NOW,last_scan_at=NOW,signals=s).should_run)

    def test_budget_and_pressure_block_dispatch(self):
        for s in [ScanSignals(budget_remaining=False),ScanSignals(resource_pressure=True),ScanSignals(provider_available=False)]:
            self.assertFalse(propose_scan(now=NOW,last_scan_at=None,signals=s).should_run)

    def test_eligible_after_cadence(self):
        p=propose_scan(now=NOW,last_scan_at=NOW-timedelta(hours=25),signals=ScanSignals())
        self.assertTrue(p.should_run)

    def test_completion_uses_same_clock_observation(self):
        # This is the exact post-claim bug that stranded the first live scan.
        end=NOW
        plan=plan_after_completed_scan(completed_at=end,signals=ScanSignals(meaningful_findings=2))
        self.assertEqual(plan.interval_hours,12)
        self.assertFalse(plan.should_run)
        self.assertEqual(plan.reason,"high_signal")

    def test_naive_timestamp_fails_closed(self):
        with self.assertRaises(ValueError):
            propose_scan(now=datetime(2026,1,1),last_scan_at=None,signals=ScanSignals())

    def test_future_scan_fails_closed(self):
        with self.assertRaises(ValueError):
            propose_scan(now=NOW,last_scan_at=NOW+timedelta(hours=1),signals=ScanSignals())

if __name__=="__main__":
    unittest.main()
