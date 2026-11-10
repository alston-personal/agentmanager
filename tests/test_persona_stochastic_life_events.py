import unittest
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from scripts.persona_pdca_tick import draw_stochastic_life_event

TZ = ZoneInfo("Asia/Taipei")

def persona(probability=1.0):
    return {"character_id":"mio-test","stochastic_life_events":{
        "enabled":True,"daily_event_probability":probability,
        "max_events_per_day":2,"minimum_gap_hours":4,
        "severity_distribution":{"minor":0.72,"moderate":0.24,"major":0.04},
        "categories":["creative","serendipity"]}}

class StochasticLifeEventTest(unittest.TestCase):
    def test_once_per_day_and_reproducible(self):
        now=datetime(2026,11,10,8,25,tzinfo=TZ)
        first=draw_stochastic_life_event(persona(),{},now,[])
        self.assertEqual(first["type"],"persona.stochastic_event")
        self.assertTrue(first["fictional_character_event"])
        self.assertFalse(first["reply_allowed"])
        self.assertFalse(first["ir_adoption_allowed"])
        state={}
        a=draw_stochastic_life_event(persona(),state,now,[])
        self.assertEqual(a,first)
        self.assertIsNone(draw_stochastic_life_event(persona(),state,now+timedelta(hours=1),[a]))

    def test_daily_roll_no_event_and_early_sleep(self):
        now=datetime(2026,11,10,8,25,tzinfo=TZ)
        state={}
        self.assertIsNone(draw_stochastic_life_event(persona(0),state,now,[]))
        self.assertEqual(state["stochastic_last_roll_date"],"2026-11-10")
        self.assertIsNone(draw_stochastic_life_event(persona(),{},now.replace(hour=6),[]))

    def test_event_dedupe_and_gap(self):
        now=datetime(2026,11,10,8,25,tzinfo=TZ)
        event=draw_stochastic_life_event(persona(),{},now,[])
        self.assertIsNone(draw_stochastic_life_event(persona(),{},now,[event]))
        following=now+timedelta(days=1)
        self.assertIsNone(draw_stochastic_life_event(
            persona(),{},following,[{"type":"persona.stochastic_event",
                "timestamp":following.isoformat(),"local_date":"2026-11-11"}]))

if __name__ == "__main__":
    unittest.main()
