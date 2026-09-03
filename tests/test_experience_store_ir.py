from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from agent_core.experience_store import experience_path, hydrate_from_one, read_experience_set, seed_experience_set


ARTIFACT = {
    "schema": "agentos.experience/v1",
    "experience_id": "core.workspace-not-continuation-authority.v1",
    "project_id": "agentos-core",
    "realm_scope": ["oracle"],
    "capability_scope": ["agentos.one.resolve"],
    "executor_scope": [],
    "kind": "constraint",
    "ir": {
        "schema": "agentos.experience-ir/v1",
        "nodes": [{
            "id": "authority",
            "op": "require",
            "predicate": "continuation.authority",
            "arguments": [{"type": "symbol", "value": "ONE_CANONICAL_IR"}],
        }],
        "entrypoints": ["authority"],
        "expected_behavior_dimensions": ["workspace_is_continuation_authority"],
    },
    "provenance": {
        "sources": ["issue://152"],
        "accepted_evidence": ["receipt://e3"],
        "extraction_id": "extract://152/authority",
    },
    "authority": {"status": "accepted", "supersedes": [], "superseded_by": []},
    "validity": {"conditions": [], "invalidated_by": []},
}


class ExperienceStoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.seed = self.root / "seed.json"
        self.seed.write_text(json.dumps({
            "schema": "agentos.experience-set/v1",
            "project_id": "agentos-core",
            "projection_only": True,
            "artifacts": [ARTIFACT],
        }), encoding="utf-8")

    def tearDown(self):
        self.tmp.cleanup()

    def _legacy(self, experience_id: str = ARTIFACT["experience_id"]):
        return {
            "schema": "agentos.experience-set/v0",
            "project_id": "agentos-core",
            "projection_only": True,
            "artifacts": [{
                "schema": "agentos.experience/v0",
                "experience_id": experience_id,
                "project_id": "agentos-core",
                "summary": "legacy display payload",
                "payload": {"workspace_is_continuation_authority": False},
            }],
        }

    def test_seed_is_idempotent_and_runtime_reads_data_layer(self):
        first = seed_experience_set(self.seed, data_root=self.root / "data")
        second = seed_experience_set(self.seed, data_root=self.root / "data")
        self.assertTrue(first["seeded"])
        self.assertFalse(second["seeded"])
        self.assertFalse(second["migrated"])
        stored = read_experience_set("agentos-core", data_root=self.root / "data")
        self.assertEqual(stored["artifacts"][0]["experience_id"], ARTIFACT["experience_id"])

    def test_existing_different_semantic_set_fails_closed(self):
        seed_experience_set(self.seed, data_root=self.root / "data")
        changed = json.loads(self.seed.read_text(encoding="utf-8"))
        changed["artifacts"][0]["ir"]["nodes"][0]["arguments"][0]["value"] = "WORKSPACE_VENDOR_HISTORY"
        other = self.root / "other.json"
        other.write_text(json.dumps(changed), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "different digest"):
            seed_experience_set(other, data_root=self.root / "data")

    def test_legacy_store_requires_explicit_migration_source(self):
        target = experience_path("agentos-core", data_root=self.root / "data")
        target.parent.mkdir(parents=True)
        target.write_text(json.dumps(self._legacy()), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "explicit known migration source"):
            seed_experience_set(self.seed, data_root=self.root / "data")

    def test_known_legacy_migrates_only_when_ids_are_preserved(self):
        target = experience_path("agentos-core", data_root=self.root / "data")
        target.parent.mkdir(parents=True)
        legacy = self._legacy()
        target.write_text(json.dumps(legacy), encoding="utf-8")
        known = self.root / "known-v0.json"
        known.write_text(json.dumps(legacy), encoding="utf-8")

        receipt = seed_experience_set(
            self.seed,
            data_root=self.root / "data",
            migrate_from=known,
        )
        self.assertTrue(receipt["migrated"])
        self.assertTrue(Path(receipt["backup_path"]).is_file())
        self.assertEqual(read_experience_set("agentos-core", data_root=self.root / "data")["schema"], "agentos.experience-set/v1")

    def test_unknown_legacy_or_id_loss_fails_closed(self):
        target = experience_path("agentos-core", data_root=self.root / "data")
        target.parent.mkdir(parents=True)
        target.write_text(json.dumps(self._legacy()), encoding="utf-8")
        wrong_known = self.root / "wrong-v0.json"
        wrong = self._legacy()
        wrong["artifacts"][0]["payload"]["extra"] = True
        wrong_known.write_text(json.dumps(wrong), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "does not match approved migration source"):
            seed_experience_set(self.seed, data_root=self.root / "data", migrate_from=wrong_known)

        target.write_text(json.dumps(self._legacy("legacy.other-id")), encoding="utf-8")
        known = self.root / "known-other-v0.json"
        known.write_text(target.read_text(encoding="utf-8"), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "add/drop accepted experience IDs"):
            seed_experience_set(self.seed, data_root=self.root / "data", migrate_from=known)

    def test_hydration_comes_from_one_store_as_ir(self):
        seed_experience_set(self.seed, data_root=self.root / "data")
        result = hydrate_from_one(
            project_id="agentos-core",
            active_goal="continue safely",
            realm="oracle",
            capabilities=("agentos.one.resolve",),
            executor="codex",
            data_root=self.root / "data",
        )
        self.assertEqual(result["source"], "ONE_EXPERIENCE")
        self.assertEqual(result["experience_ids"], [ARTIFACT["experience_id"]])
        self.assertEqual(result["items"][0]["ir"]["schema"], "agentos.experience-ir/v1")
        self.assertFalse(result["credential_exposed"])


if __name__ == "__main__":
    unittest.main()
