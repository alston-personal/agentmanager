"""Side-effect-free regression coverage for the static legacy workflow census."""
from pathlib import Path
import tempfile
import unittest

from scripts.audit_legacy_workflow_publishers import report, scan


class LegacyWorkflowPublisherCensusTest(unittest.TestCase):
    def test_scans_all_yaml_and_propagates_reusable_mutation(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            folder = root / ".github/workflows"
            folder.mkdir(parents=True)
            (folder / "deploy.yml").write_text(
                "on:\n  workflow_call:\njobs:\n  publish:\n"
                "    runs-on: ubuntu-latest\n    steps:\n"
                "      - run: bash scripts/install_oracle_runtime.sh\n",
                encoding="utf-8",
            )
            (folder / "caller.yml").write_text(
                "on:\n  push:\n    branches: [core/integration]\njobs:\n"
                "  deploy:\n    uses: ./.github/workflows/deploy.yml\n",
                encoding="utf-8",
            )
            (folder / "readonly.yaml").write_text(
                "on: [workflow_dispatch]\njobs:\n  view:\n"
                "    runs-on: ubuntu-latest\n"
                "    steps:\n      - run: echo observed\n",
                encoding="utf-8",
            )
            rows = scan(root)
            data = report(rows)
            self.assertEqual(data["workflow_count"], 3)
            by_path = {r["path"].rsplit("/", 1)[-1]: r for r in rows}
            self.assertEqual(by_path["deploy.yml"]["classification"], "mutating_signal")
            self.assertEqual(by_path["caller.yml"]["classification"], "mutating_signal")
            self.assertTrue(by_path["caller.yml"]["legacy_push"])
            self.assertEqual(by_path["readonly.yaml"]["classification"], "no_mutating_signal_observed")
            self.assertEqual(data["mutating_legacy_push_count"], 1)

    def test_unclear_workflows_never_certified_safe(self):
        with tempfile.TemporaryDirectory() as td:
            folder = Path(td) / ".github/workflows"
            folder.mkdir(parents=True)
            (folder / "ambiguous.yml").write_text(
                "on: [workflow_dispatch]\njobs:\n  x:\n"
                "    runs-on: ubuntu-latest\n"
                "    steps:\n      - run: sudo ./custom-runner\n",
                encoding="utf-8",
            )
            rows = scan(Path(td))
            self.assertEqual(rows[0]["classification"], "manual_review_required")

    def test_invalid_yaml_reported_as_unknown(self):
        with tempfile.TemporaryDirectory() as td:
            folder = Path(td) / ".github/workflows"
            folder.mkdir(parents=True)
            (folder / "invalid.yml").write_text("on: [\n", encoding="utf-8")
            row = scan(Path(td))[0]
            self.assertEqual(row["classification"], "unreadable_review_required")


if __name__ == "__main__":
    unittest.main()
