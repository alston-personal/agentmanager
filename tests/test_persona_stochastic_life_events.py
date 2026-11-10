import unittest
import subprocess
from pathlib import Path
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

    def test_minimum_spacing_and_late_emission_cursor(self):
        now=datetime(2026,11,10,21,0,tzinfo=TZ)
        receipt=evaluate(subscription(),now)
        scheduled=[datetime.fromisoformat(e["scheduled_at"].replace("Z","+00:00"))
                   for e in receipt["events"]]
        for left,right in zip(scheduled,scheduled[1:]):
            self.assertGreaterEqual((right-left).total_seconds(),4*3600)
        for e in receipt["events"]:
            self.assertEqual(e["timestamp"],now.astimezone(ZoneInfo("UTC")).isoformat().replace("+00:00","Z"))

    def test_existing_oracle_lane_routes_wake_after_durable_push(self):
        root=Path(__file__).resolve().parents[1]
        social=(root/"scripts/run_persona_social_actions_user.sh").read_text()
        pdca=(root/"scripts/run_persona_pdca_heartbeat_user.sh").read_text()
        installer=(root/"scripts/install_persona_pdca_timer_user.sh").read_text()
        workflow=(root/".github/workflows/persona-pdca-heartbeat.yml").read_text()
        self.assertIn('python3 "$EVENT_FACILITY"',social)
        self.assertIn('git -c \'credential.helper=!gh auth git-credential\' push',social)
        self.assertLess(social.index('git -c \'credential.helper=!gh auth git-credential\' push'),
                        social.rindex('if [ "$EVENT_WAKE_REQUIRED" -eq 1 ]; then request_event_wake; fi'))
        self.assertIn('systemctl --user start --no-block agentos-persona-pdca-heartbeat.service',social)
        self.assertNotIn('python3 "$EVENT_FACILITY"',pdca)
        self.assertIn('install -m 0755 "$SOURCE_EVENT_FACILITY"',installer)
        self.assertIn('"$REMOTE_EXTERNAL_INBOX" "$REMOTE_EVENT_FACILITY"',workflow)
        for sh in ("scripts/run_persona_social_actions_user.sh",
                   "scripts/run_persona_pdca_heartbeat_user.sh",
                   "scripts/install_persona_pdca_timer_user.sh"):
            result=subprocess.run(["bash","-n",str(root/sh)],capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr)

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
