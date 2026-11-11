import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from scripts.persona_external_observation_inbox import ingest, validate, observe_intel_urls

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


    def test_intel_urls_become_read_only_observations_via_existing_reader(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            intel = root / "intel_candidates.json"
            source = root / "external_observations"
            canonical = "https://www.threads.com/@oursong_alstonhuang/post/DeN9IhomVhn"
            intel.write_text(json.dumps({"candidates": [{
                "id": "4003124510509848679",
                "status": "pending_review",
                "url": "https://www.threads.net/@oursong_alstonhuang/post/DeN9IhomVhn",
                "id_provenance": "shortcode_derived_unverified",
            }]}), encoding="utf-8")
            calls = []
            def reader(url):
                calls.append(url)
                return {
                    "schema": "agentos.social.threads.public-post/v1",
                    "login_bypass_used": False, "anti_bot_bypass_used": False,
                    "source": {"url": url, "username": "oursong_alstonhuang",
                               "text": "公開內容"},
                }
            first = observe_intel_urls(intel, source, resolver=reader)
            second = observe_intel_urls(intel, source, resolver=reader)
            self.assertEqual(first["observed"], 1)
            self.assertEqual(second["already_seen"], 1)
            self.assertEqual(calls, [canonical])
            receipt = ingest(source, root / "persona")
            self.assertEqual(receipt["imported"], 1)
            stored = next((root / "persona/pdca/external_observation_inbox").glob("*.json"))
            record = json.loads(stored.read_text(encoding="utf-8"))
            self.assertEqual(record["source_url"], canonical)
            self.assertEqual(record["author"], "oursong_alstonhuang")
            self.assertFalse(record["reply_allowed"])
            self.assertNotIn("platform_object_id", record)

    def test_intel_url_observer_fails_closed_on_fake_reader_or_wrong_domain(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            intel = root / "intel.json"
            source = root / "source"
            intel.write_text(json.dumps({"candidates": [
                {"status": "pending_review", "url": "https://evil.example/@abc/post/Code"},
                {"status": "pending_review", "url": "https://www.threads.com/@other/post/Example"},
            ]}), encoding="utf-8")
            def fake_reader(url):
                return {"schema": "agentos.social.threads.public-post/v1",
                        "login_bypass_used": False, "anti_bot_bypass_used": False,
                        "source": {"url": url, "username": "another", "text": "錯誤作者"}}
            report = observe_intel_urls(intel, source, resolver=fake_reader)
            self.assertEqual(report["observed"], 0)
            self.assertEqual(report["rejected"], 2)
            self.assertFalse(source.exists())
            self.assertFalse(report["reply_allowed"])

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
        self.assertIn('--intel-file "/home/ubuntu/agent-data/personas/sunlake-milkcat/intel_candidates.json"', social)
        self.assertLess(social.index('python3 "$EXTERNAL_INBOX"'),
                        social.index('python3 "$POST_INTENT_GENERATOR"'))
        self.assertIn('install -m 0755 "$SOURCE_EXTERNAL_INBOX"', install)
        self.assertIn('"$REMOTE_WARDROBE_SOURCES" "$REMOTE_EXTERNAL_INBOX"', workflow)
        self.assertIn('"$REMOTE_EXTERNAL_INBOX" "$REMOTE_EVENT_FACILITY" "$REMOTE_EVENT_RUNNER" "$REMOTE_INSTALLER"', workflow)


if __name__ == "__main__":
    unittest.main()
