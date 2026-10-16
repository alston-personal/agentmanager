from __future__ import annotations

import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from agent_core.resolve_facade import resolve_continuation


def write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def project_entity(project_id: str) -> dict:
    return {
        "id": f"project://{project_id}",
        "kind": "project",
        "name": "LeopardCat Tarot",
        "owns": [],
        "provides": [],
        "implementation": {
            "source": {
                "repo": "alston-personal/leopardcat-tarot",
                "branch": "main",
                "canonical_path": "/home/ubuntu/leopardcat-tarot",
                "node": "oracle-core-node",
            }
        },
        "authority": {"exclusive": True},
        "state": "verified",
        "owner": "role://governance.keeper",
        "metadata": {
            "aliases": ["石虎塔羅"],
            "state": {"document": "/home/ubuntu/agent-data/projects/leopardcat-tarot/project.yaml"},
        },
    }


class TestResolveDiscovery(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.gov = self.root / "governance" / "directory.json"
        self.project_dir = self.root / "projects" / "leopardcat-tarot"
        write_json(
            self.gov,
            {
                "schema_version": "0.1",
                "entities": {"project://leopardcat-tarot": project_entity("leopardcat-tarot")},
            },
        )
        write_json(
            self.project_dir / "continuity" / "latest.json",
            {
                "protocol": "agentos.continuity-mirror/v1",
                "recommended_action": "continue",
                "canonical_ir": {
                    "schema_version": "agentos.ir/v1",
                    "ir_id": "ir_tarot",
                    "goal": "continue LeopardCat Tarot work",
                    "constraints": [],
                    "decisions": [],
                    "pending_tasks": [],
                    "continuation": {"ready_for_next_agent": True},
                },
            },
        )

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_complete_canonical_project_facts_skip_equivalent_rediscovery(self) -> None:
        result = resolve_continuation(
            "石虎塔羅",
            governance_path=self.gov,
            data_root=self.root,
        )
        self.assertTrue(result["knowledge"]["hydrated"])
        self.assertFalse(result["discovery"]["performed"])
        self.assertEqual(
            set(result["discovery"]["reused"]),
            {"project.repo", "project.branch", "project.canonical_path", "project.node"},
        )
        self.assertEqual(
            result["knowledge"]["facts"]["project.repo"]["value"],
            "alston-personal/leopardcat-tarot",
        )

    def test_resource_registry_runtime_fact_is_reused_before_discovery(self) -> None:
        now = datetime.now(timezone.utc).isoformat()
        write_json(
            self.root / "resources" / "registry.json",
            {
                "schema_version": "0.1",
                "resources": {
                    "service://leopardcat-tarot": {
                        "id": "service://leopardcat-tarot",
                        "kind": "service",
                        "labels": {"project_id": "leopardcat-tarot"},
                        "declared": {
                            "project_id": "leopardcat-tarot",
                            "service": "leopardcat-tarot.service",
                            "port": 8088,
                        },
                        "observed": {
                            "git": {
                                "origin": "https://user:secret@github.com/alston-personal/leopardcat-tarot.git",
                                "branch": "main",
                                "commit": "abc123",
                            }
                        },
                        "verification": {
                            "status": "verified",
                            "last_verified_at": now,
                            "ttl_seconds": 3600,
                            "errors": [],
                        },
                    }
                },
            },
        )
        result = resolve_continuation(
            "leopardcat-tarot",
            governance_path=self.gov,
            data_root=self.root,
            discovery_requirements=[
                {
                    "fact_key": "runtime.service",
                    "depth": "runtime",
                    "evidence_strength": "verified",
                },
                {
                    "fact_key": "runtime.git.remote",
                    "depth": "runtime",
                    "evidence_strength": "verified",
                },
            ],
        )
        self.assertFalse(result["discovery"]["performed"])
        self.assertEqual(result["discovery"]["reused"], ["runtime.service", "runtime.git.remote"])
        self.assertEqual(
            result["knowledge"]["facts"]["runtime.git.remote"]["value"],
            "https://github.com/alston-personal/leopardcat-tarot.git",
        )
        self.assertNotIn("secret", json.dumps(result, ensure_ascii=False))

    def test_stale_resource_fact_requires_targeted_revalidation(self) -> None:
        write_json(
            self.root / "resources" / "registry.json",
            {
                "schema_version": "0.1",
                "resources": {
                    "service://leopardcat-tarot": {
                        "id": "service://leopardcat-tarot",
                        "kind": "service",
                        "labels": {"project_id": "leopardcat-tarot"},
                        "declared": {"service": "leopardcat-tarot.service"},
                        "observed": {},
                        "verification": {
                            "status": "verified",
                            "last_verified_at": "2020-01-01T00:00:00+00:00",
                            "ttl_seconds": 60,
                            "errors": [],
                        },
                    }
                },
            },
        )
        result = resolve_continuation(
            "leopardcat-tarot",
            governance_path=self.gov,
            data_root=self.root,
            discovery_requirements=[
                {
                    "fact_key": "runtime.service",
                    "depth": "runtime",
                    "evidence_strength": "observed",
                }
            ],
        )
        self.assertTrue(result["discovery"]["performed"])
        self.assertEqual(result["discovery"]["rediscovery_reasons"], ["stale"])

    def test_sensitive_material_in_continuation_is_redacted(self) -> None:
        write_json(
            self.project_dir / "continuity" / "latest.json",
            {
                "protocol": "agentos.continuity-mirror/v1",
                "recommended_action": "continue",
                "canonical_ir": {
                    "schema_version": "agentos.ir/v1",
                    "ir_id": "ir_secret",
                    "goal": "continue",
                    "authorization": "Bearer should-not-persist",
                    "remote": "https://user:secret@git.example.test/team/repo.git",
                },
            },
        )
        result = resolve_continuation(
            "leopardcat-tarot",
            governance_path=self.gov,
            data_root=self.root,
        )
        serialized = json.dumps(result, ensure_ascii=False)
        self.assertNotIn("should-not-persist", serialized)
        self.assertNotIn("user:secret", serialized)


if __name__ == "__main__":
    unittest.main()
