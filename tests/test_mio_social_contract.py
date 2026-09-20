"""Regression tests for Mio's persistent Threads decision path.

These tests never connect to Threads, Oracle or any external account; the real
platform receipts are checked separately by the governed publish workflows.
"""
import json
import unittest
from unittest.mock import patch

from scripts import mio_persona_social_loop_user as mio


class MioSocialContractTests(unittest.TestCase):
    def test_agy_cli_envelope_accepts_only_matching_comment_decision(self):
        decision={"reply_id":"18124006117843631","should_reply":True,
                  "delay_minutes":30,"text":"謝謝你的分享 🌱","reason_category":"relationship"}
        envelope=json.dumps({"content":json.dumps({"decisions":[decision]},ensure_ascii=False)},ensure_ascii=False)
        result=mio.extract_reply_decisions("AGY completed\n"+envelope,{"18124006117843631"})
        self.assertEqual(result["decisions"],[decision])

    def test_echoed_prompt_schema_is_not_an_actionable_decision(self):
        template='Prompt echo: {"decisions":[{"reply_id":"...","should_reply":true,"text":"..."}]}'
        with self.assertRaisesRegex(ValueError,"missing_expected_ids"):
            mio.extract_reply_decisions(template,{"18124006117843631"})

    def test_wrong_comment_id_and_boolean_string_are_rejected(self):
        response=json.dumps({"decisions":[
            {"reply_id":"different","should_reply":True,"text":"wrong"},
            {"reply_id":"18124006117843631","should_reply":"true","text":"wrong"}
        ]})
        with self.assertRaisesRegex(ValueError,"missing_expected_ids"):
            mio.extract_reply_decisions(response,{"18124006117843631"})

    def test_only_expected_comment_can_be_selected(self):
        response=json.dumps({"decisions":[
            {"reply_id":"other-comment","should_reply":True,"text":"wrong"},
            {"reply_id":"18124006117843631","should_reply":False,"text":None}
        ]})
        result=mio.extract_reply_decisions(response,{"18124006117843631"})
        self.assertEqual(result["decisions"],[
            {"reply_id":"18124006117843631","should_reply":False,"text":None}
        ])

    def test_manual_reply_prevents_autonomous_duplicate(self):
        own={"id":"own-reply","is_reply_owned_by_me":True,
             "replied_to":{"id":"18124006117843631"}}
        with patch.object(mio,"post",return_value=(200,{"ok":True,"result":{"items":[own]}})):
            self.assertTrue(mio.already_replied("test-key","test-binding","owned-root","18124006117843631"))
            self.assertFalse(mio.already_replied("test-key","test-binding","owned-root","unanswered"))

    def test_failed_reply_read_cannot_be_treated_as_unanswered(self):
        with patch.object(mio,"post",return_value=(500,{"ok":False})):
            self.assertIsNone(mio.already_replied("test-key","test-binding","owned-root","18124006117843631"))


    def test_publish_readback_requires_own_matching_id_parent_and_text(self):
        own={"id":"our-200","is_reply_owned_by_me":True,
             "replied_to":{"id":"reader-100"},"text":"回覆內容"}
        other={"id":"not-our-201","is_reply_owned_by_me":False,
               "replied_to":{"id":"reader-100"},"text":"回覆內容"}
        with patch.object(mio,"post",return_value=(200,{"ok":True,"result":{"items":[other,own]}})):
            self.assertEqual(mio.verify_reply_readback("key","binding","root","reader-100","回覆內容","our-200"),("verified","our-200"))
            self.assertEqual(mio.verify_reply_readback("key","binding","root","reader-100","回覆內容","wrong-id"),("not_found",""))
            self.assertEqual(mio.verify_reply_readback("key","binding","root","reader-100","不同內容","our-200"),("not_found",""))

    def test_unavailable_reply_readback_cannot_confirm_publication(self):
        with patch.object(mio,"post",return_value=(503,{"ok":False})):
            self.assertEqual(mio.verify_reply_readback("key","binding","root","reader-100","回覆內容","our-200"),("unavailable",""))


if __name__=="__main__":
    unittest.main()
