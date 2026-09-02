from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from agent_core.experience_store import read_experience_set, seed_experience_set, hydrate_from_one


ARTIFACT = {
    "schema": "agentos.experience/v0",
    "experience_id": "x.v1",
    "project_id": "agentos-core",
    "realm_scope": ["oracle"],
    "capability_scope": ["repository.merge"],
    "executor_scope": ["codex"],
    "kind": "constraint",
    "summary": "Generic continue is not merge authority.",
    "payload": {"generic_continue_is_authorization": False},
    "provenance": {"sources": ["test://source"], "accepted_evidence": []},
    "authority": {"status": "accepted", "supersedes": [], "superseded_by": []},
    "validity": {"conditions": [], "invalidated_by": []},
}


class ExperienceStoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.seed = self.root / "seed.json"
        self.seed.write_text(json.dumps({
            "schema": "agentos.experience-set/v0",
            "project_id": "agentos-core",
            "projection_only": True,
            "artifacts": [ARTIFACT],
        }), encoding="utf-8")

    def tearDown(self):
        self.tmp.cleanup()

    def test_seed_is_idempotent_and_runtime_reads_data_layer(self):
        first = seed_experience_set(self.seed, data_root=self.root / "data")
        second = seed_experience_set(self.seed, data_root=self.root / "data")
        self.assertTrue(first["seeded"])
        self.assertFalse(second["seeded"])
        stored = read_experience_set("agentos-core", data_root=self.root / "data")
        self.assertEqual(stored["artifacts"][0]["experience_id"], "x.v1")
        self.assertFalse(first["credential_exposed"])

    def test_existing_different_set_fails_closed(self):
        seed_experience_set(self.seed, data_root=self.root / "data")
        changed = json.loads(self.seed.read_text(encoding="utf-8"))
        changed["artifacts"][0]["summary"] = "changed"
        other = self.root / "other.json"
        other.write_text(json.dumps(changed), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "different digest"):
            seed_experience_set(other, data_root=self.root / "data")

    def test_hydration_comes_from_one_store(self):
        seed_experience_set(self.seed, data_root=self.root / "data")
        result = hydrate_from_one(
            project_id="agentos-core",
            active_goal="continue safely",
            realm="oracle",
            capabilities=("repository.merge",),
            executor="codex",
            data_root=self.root / "data",
        )
        self.assertEqual(result["source"], "ONE_EXPERIENCE")
        self.assertEqual(result["experience_ids"], ["x.v1"])
        self.assertFalse(result["credential_exposed"])


if __name__ == "__main__":
    unittest.main()
