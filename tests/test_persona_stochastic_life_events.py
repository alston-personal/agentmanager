import unittest
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from scripts.agentos_event_facility import evaluate, validate_subscription

TZ=ZoneInfo("Asia/Taipei")

def subscription(p=1.0):
    return {
        "schema":"agentos.event.subscription/v1",
        "subscription_id":"test.mio.daily-life",
        "target":"persona:sunlake-milkcat",
        "trigger":{"kind":"stochastic","model":"daily_count",
                   "probability_per_day":p,"max_events_per_day":2,
                   "min_gap_hours":4,"timezone":"Asia/Taipei","earliest_hour":8},
        "delivery":{"mode":"next_cycle"},
        "severity_distribution":{"minor":0.72,"moderate":0.24,"major":0.04},
        "definitions":[{"id":"creative","summary":"fictional inspiration","fictional":True,
                        "temporary_effect":{"energy_delta":1,"mood_delta":1}}]}

class EventFacilityTest(unittest.TestCase):
    def test_deterministic_and_idempotent(self):
        now=datetime(2026,11,10,20,30,tzinfo=TZ)
        a=evaluate(subscription(),now)
        self.assertEqual(a,evaluate(subscription(),now))
        self.assertIn(a["planned_count"],(1,2))
        self.assertEqual(len(a["events"]),a["planned_count"])
        self.assertEqual(evaluate(subscription(),now,a["events"])["events"],[])
        self.assertTrue(all(not x["reply_allowed"] and not x["ir_adoption_allowed"] for x in a["events"]))
        self.assertTrue(all(x["target"]=="persona:sunlake-milkcat" for x in a["events"]))

    def test_probability_is_daily_not_per_tick(self):
        now=datetime(2026,11,10,21,0,tzinfo=TZ)
        self.assertEqual(evaluate(subscription(0),now)["planned_count"],0)
        self.assertEqual(evaluate(subscription(0),now+timedelta(minutes=5))["planned_count"],0)

    def test_invalid_subscription_rejected(self):
        data=subscription()
        data["definitions"][0]["temporary_effect"]["execute_shell"]="rm -rf /"
        with self.assertRaises(ValueError):
            validate_subscription(data)
        data=subscription()
        data["definitions"][0]["fictional"]=False
        with self.assertRaises(ValueError):
            validate_subscription(data)

    def test_no_early_event_and_replay_after_due(self):
        date=datetime(2026,11,10,7,0,tzinfo=TZ)
        self.assertEqual(evaluate(subscription(),date)["events"],[])
        self.assertGreaterEqual(evaluate(subscription(),date.replace(hour=21))["due_emitted"],1)

if __name__=="__main__":
    unittest.main()
