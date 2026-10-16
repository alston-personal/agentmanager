import unittest
from unittest.mock import patch

from scripts.osworld_worker_preflight import inspect_worker


class OSWorldWorkerPreflightTests(unittest.TestCase):
    @patch("scripts.osworld_worker_preflight.platform.machine", return_value="aarch64")
    def test_arm_host_is_control_only_for_docker(self, _machine):
        with patch("scripts.osworld_worker_preflight.shutil.which", return_value=None):
            result = inspect_worker("docker", env={}, root=__import__("pathlib").Path("/definitely-missing"))
        self.assertFalse(result["ready"])
        self.assertIn("x86_64_host", result["blocking_failures"])
        self.assertEqual(result["recommended_role"], "control-orchestrator-only")

    @patch("scripts.osworld_worker_preflight.platform.machine", return_value="x86_64")
    def test_aws_requires_official_region_and_credentials(self, _machine):
        result = inspect_worker("aws", env={
            "AWS_REGION": "us-west-2",
            "AWS_SUBNET_ID": "s",
            "AWS_SECURITY_GROUP_ID": "g",
            "AWS_ACCESS_KEY_ID": "k",
            "AWS_SECRET_ACCESS_KEY": "s",
            "HF_TOKEN": "hf",
            "WEBSITE_HOST_SUFFIX": "example.invalid",
        })
        self.assertFalse(result["ready"])
        self.assertIn("aws_region_us_east_1", result["blocking_failures"])

    @patch("scripts.osworld_worker_preflight.platform.machine", return_value="x86_64")
    def test_aws_ready_with_required_prerequisites(self, _machine):
        result = inspect_worker("aws", env={
            "AWS_REGION": "us-east-1",
            "AWS_SUBNET_ID": "s",
            "AWS_SECURITY_GROUP_ID": "g",
            "AWS_ACCESS_KEY_ID": "k",
            "AWS_SECRET_ACCESS_KEY": "s",
            "HF_TOKEN": "hf",
            "WEBSITE_HOST_SUFFIX": "bench.example",
        })
        self.assertTrue(result["ready"])
        self.assertEqual(result["recommended_role"], "benchmark-worker")


if __name__ == "__main__":
    unittest.main()
