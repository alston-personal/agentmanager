import json
import tempfile
import unittest
from pathlib import Path

from agent_core.credit_ledger import CreditLedger
from agent_core.platform_execution import PlatformExecutionStore
from agent_core.studio_capability_adapter import sync_studio_release_capabilities


class PlatformExecutionTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        root = Path(self.temp_dir.name)
        self.registry = root / "directory.json"
        self.receipts = root / "receipts"
        self.ledger = CreditLedger(root / "credits.sqlite3")
        self.registry.write_text(
            json.dumps(
                {
                    "schema_version": "0.1",
                    "updated_at": None,
                    "entities": {
                        "service://studio.static-route.release": {
                            "id": "service://studio.static-route.release",
                            "kind": "service",
                            "state": "implemented",
                            "owns": [],
                            "provides": ["capability://studio.static-route.release"],
                            "implementation": {"workflow": "shared-release.yml"},
                            "authority": {
                                "exclusive": False,
                                "reuse_before_build": True,
                            },
                        }
                    },
                }
            ),
            encoding="utf-8",
        )
        self.store = PlatformExecutionStore(
            ledger=self.ledger,
            governance_path=self.registry,
            receipt_root=self.receipts,
        )
        self.ledger.grant("acct", 100, "seed")

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_success_path_reuses_capability_and_commits_credits(self):
        prepared = self.store.prepare(
            execution_id="milkcat-world-run-1",
            account_id="acct",
            required_capabilities=["studio.static-route.release"],
            credit_cost=10,
            metadata={"route": "world"},
        )
        self.assertEqual(prepared["status"], "prepared")
        self.assertEqual(prepared["resolution"]["mode"], "reuse")
        self.assertEqual(
            prepared["resolution"]["selectedCandidateIds"],
            ["service://studio.static-route.release"],
        )
        self.assertEqual(self.ledger.summary("acct")["reserved"], 10)

        settled = self.store.settle(
            "milkcat-world-run-1",
            succeeded=True,
            metadata={"public_acceptance": "PASS"},
        )
        self.assertEqual(settled["status"], "succeeded")
        self.assertEqual(settled["credits"]["committedAmount"], 10)
        self.assertEqual(settled["credits"]["releasedAmount"], 0)
        self.assertEqual(self.ledger.summary("acct")["balance"], 90)
        self.assertEqual(self.ledger.summary("acct")["reserved"], 0)

    def test_failure_path_releases_full_reservation(self):
        self.store.prepare(
            execution_id="milkcat-world-run-2",
            account_id="acct",
            required_capabilities=["studio.static-route.release"],
            credit_cost=10,
        )
        settled = self.store.settle("milkcat-world-run-2", succeeded=False)
        self.assertEqual(settled["status"], "failed")
        self.assertEqual(settled["credits"]["committedAmount"], 0)
        self.assertEqual(settled["credits"]["releasedAmount"], 10)
        self.assertEqual(self.ledger.summary("acct")["balance"], 100)
        self.assertEqual(self.ledger.summary("acct")["reserved"], 0)

    def test_success_can_commit_less_and_release_remainder(self):
        self.store.prepare(
            execution_id="milkcat-world-run-3",
            account_id="acct",
            required_capabilities=["studio.static-route.release"],
            credit_cost=10,
        )
        settled = self.store.settle(
            "milkcat-world-run-3", succeeded=True, actual_cost=6
        )
        self.assertEqual(settled["credits"]["committedAmount"], 6)
        self.assertEqual(settled["credits"]["releasedAmount"], 4)
        self.assertEqual(self.ledger.summary("acct")["balance"], 94)

    def test_prepare_and_settle_are_idempotent(self):
        first = self.store.prepare(
            execution_id="same-run",
            account_id="acct",
            required_capabilities=["studio.static-route.release"],
            credit_cost=10,
        )
        second = self.store.prepare(
            execution_id="same-run",
            account_id="acct",
            required_capabilities=["studio.static-route.release"],
            credit_cost=10,
        )
        self.assertEqual(first, second)
        first_final = self.store.settle("same-run", succeeded=True)
        second_final = self.store.settle("same-run", succeeded=True)
        self.assertEqual(first_final, second_final)
        operations = [entry["operation"] for entry in self.ledger.entries("acct")]
        self.assertEqual(operations.count("reserve"), 1)
        self.assertEqual(operations.count("commit"), 1)

    def test_missing_capability_is_denied_before_reservation(self):
        with self.assertRaises(PermissionError):
            self.store.prepare(
                execution_id="missing-run",
                account_id="acct",
                required_capabilities=["nonexistent.capability"],
                credit_cost=10,
            )
        self.assertEqual(self.ledger.summary("acct")["reserved"], 0)

    def test_same_execution_id_cannot_change_cost(self):
        self.store.prepare(
            execution_id="same-run",
            account_id="acct",
            required_capabilities=["studio.static-route.release"],
            credit_cost=10,
        )
        with self.assertRaisesRegex(ValueError, "different platform parameters"):
            self.store.prepare(
                execution_id="same-run",
                account_id="acct",
                required_capabilities=["studio.static-route.release"],
                credit_cost=11,
            )


class StudioCapabilityAdapterTests(unittest.TestCase):
    def test_canonical_studio_registry_mirrors_into_directory(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source = root / "studio.yaml"
            directory = root / "directory.json"
            source.write_text(
                """schema_version: '0.1'
capabilities:
  studio_static_route_release:
    provider_id: service://studio.static-route.release
    capability_uri: capability://studio.static-route.release
    state: implemented
    status: extracted-first-consumer
    canonical_workflow: .github/workflows/reusable-studio-static-route-release.yml
    source_repo: alston-personal/studio-web
""",
                encoding="utf-8",
            )
            entities = sync_studio_release_capabilities(
                source_path=source, directory_path=directory
            )
            self.assertEqual(len(entities), 1)
            data = json.loads(directory.read_text(encoding="utf-8"))
            mirrored = data["entities"]["service://studio.static-route.release"]
            self.assertEqual(
                mirrored["provides"], ["capability://studio.static-route.release"]
            )
            self.assertTrue(
                mirrored["authority"]["canonical_capability_contract"]
            )


if __name__ == "__main__":
    unittest.main()
