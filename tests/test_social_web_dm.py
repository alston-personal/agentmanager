import unittest

from agentos_node.social.web_dm import DirectMessageEvent, dedupe_new_events
from agentos_node.social.persona_dm import account_from_profile_hrefs


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


class PersonaIdentityTests(unittest.TestCase):
    def test_profile_href_resolves_allowlisted_persona(self):
        self.assertEqual(account_from_profile_hrefs(["/@mio.milkcat"]), "mio.milkcat")
        self.assertEqual(
            account_from_profile_hrefs(["https://www.threads.com/@oursong_alstonhuang"]),
            "oursong_alstonhuang",
        )

    def test_unknown_or_ambiguous_profile_href_fails_closed(self):
        self.assertIsNone(account_from_profile_hrefs(["/@someone_else"]))
        self.assertIsNone(
            account_from_profile_hrefs(["/@mio.milkcat", "/@oursong_alstonhuang"])
        )


    def test_threads_bridge_identity_selector_covers_nested_profile_icon(self):
        from pathlib import Path
        text = Path("scripts/threads_web_dm_bridge_user.py").read_text(encoding="utf-8")
        self.assertIn('a[href]:has(svg[aria-label*="profile" i])', text)
        self.assertIn('[role="navigation"] a[href^="/@"]', text)


if __name__=="__main__":
    unittest.main()


def test_dm_read_stages_only_runtime_tree():
    repo=Path(__file__).resolve().parents[1]
    text=(repo/"scripts"/"run_threads_web_dm_read_user.sh").read_text(encoding="utf-8")
    assert 'archive "$SOURCE_COMMIT" agentos_node scripts' in text
    assert 'archive "$SOURCE_COMMIT" | tar' not in text


def test_mio_resume_uses_same_cdp_binding_as_dm_runtime():
    general=(Path(__file__).resolve().parents[1]/"scripts"/"resume_threads_persona_login_user.sh").read_text(encoding="utf-8")
    legacy=(Path(__file__).resolve().parents[1]/"scripts"/"resume_mio_threads_login_user.sh").read_text(encoding="utf-8")
    assert 'mio) ACCOUNT="mio.milkcat"; BASE="http://127.0.0.1:9224"' in general
    assert 'BASE="http://127.0.0.1:9224"' in legacy

def test_dm_read_attempts_safe_resume_for_mio_too():
    text=(Path(__file__).resolve().parents[1]/"scripts"/"run_threads_web_dm_read_user.sh").read_text(encoding="utf-8")
    assert 'AGENTOS_DM_PERSONA="$PERSONA" bash "$STAGE/scripts/resume_threads_persona_login_user.sh"' in text
    assert 'mio_autonomous_after_resume' in text
