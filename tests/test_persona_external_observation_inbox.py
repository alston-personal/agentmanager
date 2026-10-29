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


if __name__ == "__main__":
    unittest.main()
