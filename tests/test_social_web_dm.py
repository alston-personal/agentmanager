import unittest

from agentos_node.social.web_dm import DirectMessageEvent, dedupe_new_events


class DirectMessageEventTests(unittest.TestCase):
    def test_dedupe_is_message_id_scoped(self):
        a=DirectMessageEvent("threads","mio","c1","m1",None,"alice","hi",None)
        b=DirectMessageEvent("threads","mio","c1","m2",None,"alice","again",None)
        self.assertEqual([x.message_id for x in dedupe_new_events([a,b],{"m1"})],["m2"])

    def test_event_contract_is_platform_neutral(self):
        event=DirectMessageEvent("instagram","oursong","c9","m9",None,"bob","hello",None)
        payload=event.to_dict()
        self.assertEqual(payload["schema"],"agentos.social-conversation-event/v1")
        self.assertEqual(payload["platform"],"instagram")
        self.assertEqual(payload["source"],"web_bridge")


if __name__=="__main__":
    unittest.main()
