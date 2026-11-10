import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from scripts.persona_external_observation_inbox import ingest, validate

URL = "https://www.threads.com/@oursong_alstonhuang/post/DeN9IhomVhn"


def observation():
    return {"schema": "agentos.mio-external-public-observation/v1",
            "source": "vendor-public-threads-reader", "source_url": URL,
            "author": "oursong_alstonhuang", "text": "Public external post",
            "observed_at": "2026-10-16T04:58:25Z", "decision": "UNDECIDED",
            "reply_allowed": False, "ir_adoption_allowed": False,
            "write_performed": False}


class TestInbox(unittest.TestCase):
    def test_validates_no_write_provenance(self):
        self.assertIsNotNone(validate(observation()))
        bad = observation()
        bad["reply_allowed"] = True
        self.assertIsNone(validate(bad))
        bad = observation()
        bad["author"] = "mio.milkcat"
        self.assertIsNone(validate(bad))

    def test_durable_import_and_dedupe(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            src, persona = root / "oracle", root / "persona"
            src.mkdir()
            digest = hashlib.sha256(URL.encode()).hexdigest()[:24]
            (src / (digest + ".json")).write_text(json.dumps(observation()), encoding="utf-8")
            first = ingest(src, persona)
            second = ingest(src, persona)
            self.assertEqual(first["imported"], 1)
            self.assertEqual(second["already_seen"], 1)
            written = json.loads((persona / "pdca" / "external_observation_inbox" / (digest + ".json")).read_text())
            self.assertFalse(written["ir_adoption_allowed"])

    def test_rejects_wrong_filename_and_missing(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            self.assertEqual(ingest(root / "absent", root)["status"], "BLOCKED")
            src = root / "oracle"
            src.mkdir()
            (src / "wrong.json").write_text(json.dumps(observation()), encoding="utf-8")
            self.assertEqual(ingest(src, root)["rejected"], 1)


    def test_owner_historical_reading_is_scoped_and_never_grants_reply(self):
        # Older verified observations remain visible only if their exact URL
        # is explicitly approved by Mio's persona configuration.
        root = Path(__file__).resolve().parents[1]
        generator = (root / "scripts/persona_post_intent_generator.py").read_text()
        self.assertIn('cfg.get("approved_historical_external_read_urls")', generator)
        self.assertIn('observed["source_url"] not in approved_historical_urls', generator)
        self.assertIn('"historical_context_only":not fresh', generator)
        self.assertIn('"freshness":"recent" if fresh else "historical_owner_approved"', generator)
        self.assertIn('"reply_allowed":False,"ir_adoption_allowed":False', generator)

    def test_oracle_local_social_lane_installs_and_imports_before_reasoning(self):
        root = Path(__file__).resolve().parents[1]
        social = (root / "scripts/run_persona_social_actions_user.sh").read_text()
        install = (root / "scripts/install_persona_pdca_timer_user.sh").read_text()
        workflow = (root / ".github/workflows/persona-pdca-heartbeat.yml").read_text()
        self.assertIn('python3 "$EXTERNAL_INBOX"', social)
        self.assertLess(social.index('python3 "$EXTERNAL_INBOX"'),
                        social.index('python3 "$POST_INTENT_GENERATOR"'))
        self.assertIn('install -m 0755 "$SOURCE_EXTERNAL_INBOX"', install)
        self.assertIn('"$REMOTE_WARDROBE_SOURCES" "$REMOTE_EXTERNAL_INBOX"', workflow)
        self.assertIn('"$REMOTE_EXTERNAL_INBOX" "$REMOTE_EVENT_FACILITY" "$REMOTE_EVENT_RUNNER" "$REMOTE_INSTALLER"', workflow)


if __name__ == "__main__":
    unittest.main()
