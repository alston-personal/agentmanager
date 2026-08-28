import json
import tempfile
import unittest
from pathlib import Path

from agent_core.resolve_facade import resolve_continuation, resolve_project_identity


def write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def project_entity(project_id: str, *, name: str | None = None, aliases=None) -> dict:
    return {
        "id": f"project://{project_id}",
        "kind": "project",
        "name": name or project_id,
        "owns": [],
        "provides": [],
        "implementation": {},
        "authority": {"exclusive": False},
        "state": "observed",
        "owner": None,
        "supersedes": None,
        "last_verified_at": None,
        "metadata": {"aliases": list(aliases or [])},
    }


class TestResolveFacade(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.gov = self.root / "governance" / "directory.json"
        self.projects = self.root / "projects"

    def tearDown(self):
        self.tmp.cleanup()

    def write_governance(self, *entities: dict) -> None:
        write_json(
            self.gov,
            {
                "schema_version": "0.1",
                "updated_at": None,
                "entities": {entity["id"]: entity for entity in entities},
            },
        )

    def test_alias_resolves_only_from_governance_project_entity(self):
        self.write_governance(
            project_entity("metashield-protocol", name="MetaShield Protocol", aliases=["chamber", "echo"])
        )
        (self.projects / "metashield-protocol").mkdir(parents=True)

        resolved = resolve_project_identity(
            "echo",
            governance_path=self.gov,
            data_root=self.root,
        )

        self.assertEqual(resolved["id"], "metashield-protocol")
        self.assertEqual(resolved["resolution"], "alias")
        self.assertEqual(resolved["identity_source"], "governance-directory")
        self.assertIn("chamber", resolved["aliases"])

    def test_application_identity_registry_does_not_create_project_alias(self):
        self.write_governance()
        project_dir = self.projects / "metashield-protocol"
        project_dir.mkdir(parents=True)
        write_json(
            project_dir / "identity-registry.json",
            {"aliases": {"chamber": {"display_name": "Chamber"}}},
        )

        with self.assertRaises(KeyError):
            resolve_project_identity(
                "chamber",
                governance_path=self.gov,
                data_root=self.root,
            )

    def test_exact_project_id_has_conservative_migration_fallback(self):
        self.write_governance()
        (self.projects / "metashield-protocol").mkdir(parents=True)

        resolved = resolve_project_identity(
            "metashield-protocol",
            governance_path=self.gov,
            data_root=self.root,
        )

        self.assertEqual(resolved["id"], "metashield-protocol")
        self.assertEqual(resolved["aliases"], [])
        self.assertEqual(resolved["identity_source"], "project-data-exact-id-fallback")

    def test_ambiguous_alias_is_rejected_instead_of_guessed(self):
        self.write_governance(
            project_entity("alpha", aliases=["shared"]),
            project_entity("beta", aliases=["shared"]),
        )

        with self.assertRaisesRegex(ValueError, "ambiguous project identity"):
            resolve_project_identity(
                "shared",
                governance_path=self.gov,
                data_root=self.root,
            )

    def test_continuation_envelope_composes_ir_and_execution_head(self):
        self.write_governance(project_entity("agentos-core", aliases=["core"]))
        project_dir = self.projects / "agentos-core"
        project_dir.mkdir(parents=True)
        write_json(
            project_dir / "execution-head.json",
            {
                "schema": "agentos.execution-head/v1",
                "project_id": "agentos-core",
                "node": "oracle-core-node",
                "branch": "main",
                "local_head": "abc123",
            },
        )
        write_json(
            project_dir / "continuity" / "latest.json",
            {
                "protocol": "agentos.continuity-mirror/v1",
                "project_id": "agentos-core",
                "recommended_action": "continue",
                "canonical_ir": {
                    "schema_version": "agentos.ir/v1",
                    "project_id": "agentos-core",
                    "ir_id": "ir_test",
                    "parent_ir_id": "ir_parent",
                    "goal": "close ChatGPT Web -> ONE resolve path",
                    "constraints": ["do not guess aliases"],
                    "decisions": [],
                    "pending_tasks": ["verify endpoint"],
                    "continuation": {"ready_for_next_agent": True},
                    "capability": "agentos.project.continue",
                },
            },
        )

        result = resolve_continuation(
            "core",
            governance_path=self.gov,
            data_root=self.root,
            node_context={"node_id": "chatgpt-web-test"},
        )

        self.assertEqual(result["schema"], "agentos.resolve/v1")
        self.assertEqual(result["project"]["id"], "agentos-core")
        self.assertEqual(result["active_goal"], "close ChatGPT Web -> ONE resolve path")
        self.assertEqual(result["execution_head"]["local_head"], "abc123")
        self.assertEqual(result["continuation"]["ir_id"], "ir_test")
        self.assertEqual(result["next_action"], "continue")
        self.assertTrue(result["availability"]["continuation"])
        self.assertFalse(result["availability"]["last_receipt"])


if __name__ == "__main__":
    unittest.main()
