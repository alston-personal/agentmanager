import json
import unittest
from pathlib import Path


REGISTRY = Path(__file__).resolve().parents[1] / "governance" / "product-deployment-carriers.json"
NO_JOB_CLASS = "legacy_product_integration_carrier_validation_noise_observed"


class ProductDeploymentCarrierRegistryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = json.loads(REGISTRY.read_text(encoding="utf-8"))
        cls.carriers = cls.data["carriers"]

    def test_schema_and_worker_are_canonical(self):
        self.assertEqual(
            self.data["schema"],
            "agentos.product-deployment-carriers/v0",
        )
        self.assertEqual(self.data["worker_issue"], 175)

    def test_workflow_paths_are_unique(self):
        workflows = [item["workflow"] for item in self.carriers]
        self.assertEqual(len(workflows), len(set(workflows)))

    def test_observed_no_job_runs_cannot_be_transport_or_runtime_evidence(self):
        observed = [
            item for item in self.carriers
            if item.get("classification") == NO_JOB_CLASS
        ]
        self.assertGreaterEqual(len(observed), 2)
        for item in observed:
            self.assertEqual(item.get("observed_jobs"), 0)
            self.assertFalse(item.get("observed_runner_claim"))
            self.assertFalse(item.get("observed_privileged_execution"))
            self.assertEqual(
                item.get("observed_runtime_side_effect"),
                "none_from_this_run",
            )
            self.assertFalse(item.get("transport_routing_evidence"))

    def test_known_no_job_noise_is_persisted(self):
        by_workflow = {item["workflow"]: item for item in self.carriers}
        layout = by_workflow[
            ".github/workflows/oracle-integrate-layoutlab-official-site.yml"
        ]
        vendor = by_workflow[
            ".github/workflows/oracle-integrate-vendor-reputation.yml"
        ]
        self.assertEqual(layout["observed_run"], 33456886112)
        self.assertEqual(vendor["observed_run"], 33456886833)
        self.assertEqual(layout["observed_jobs"], 0)
        self.assertEqual(vendor["observed_jobs"], 0)

    def test_registry_preserves_working_carrier_invariant(self):
        self.assertIn(
            "working_carriers_are_preserved_until_verified_replacements_exist",
            self.data["invariants"],
        )


if __name__ == "__main__":
    unittest.main()
