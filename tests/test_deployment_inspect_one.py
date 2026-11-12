"""Contract tests: real ONE routing, no privileged deployment or false release claims."""
from __future__ import annotations
import unittest
from pathlib import Path
from unittest.mock import patch
from agent_core.executor_job_contract import canonical_executor_job_request, validate_executor_job, ExecutorJobContractError
from agentos_node.deployment_inspect_provider import _status, register_deployment_inspection_providers
from agentos_node.executor_job_adapter import ExecutorJobProviderRegistry, run_registered_executor_job

class DeploymentInspectOneTests(unittest.TestCase):
    def test_two_registered_fixed_read_only_jobs(self):
        for job in ("deployment.agentos.inspect", "deployment.studio.inspect"):
            req = canonical_executor_job_request(job)
            self.assertEqual(req["authority"], "bounded-read-only")
            self.assertEqual(req["executor_class"], "oracle-deployment-inspector")
            self.assertEqual(validate_executor_job(req).job_type, job)
        registry = ExecutorJobProviderRegistry()
        self.assertTrue(register_deployment_inspection_providers(registry))
        self.assertTrue(register_deployment_inspection_providers(registry))
        for job in ("deployment.agentos.inspect", "deployment.studio.inspect"):
            self.assertIsNotNone(registry.get(job))

    def test_no_caller_supplied_runtime_paths_or_commands(self):
        req = canonical_executor_job_request("deployment.studio.inspect")
        for key, value in (("command", "cat /etc/nginx/nginx.conf"),
                           ("path", "/etc/shadow"),
                           ("env", {"OVERRIDE": "true"}),
                           ("target_id", "another-target")):
            with self.subTest(key=key), self.assertRaises(ExecutorJobContractError):
                validate_executor_job({**req, key: value})
        with self.assertRaises(ExecutorJobContractError):
            validate_executor_job({**req, "workload_ref": "site://agentos.milkcat.org"})

    @patch("agentos_node.deployment_inspect_provider._http")
    @patch("agentos_node.deployment_inspect_provider.SITEFILE")
    def test_legacy_studio_sitefile_fails_even_with_public_200(self, sitefile, http):
        sitefile.resolve.return_value = Path("/etc/nginx/sites-available/studio.milkcat.org")
        sitefile.read_text.return_value = "server {\n root /home/ubuntu/zeus-writer/website/dist;\n}"
        http.return_value = (200, "studio-web-production-root/v1")
        result = _status("deployment.studio.inspect")
        self.assertEqual(result["classification"], "STUDIO_LEGACY_SITEFILE")
        self.assertFalse(result["successful"])

    @patch("agentos_node.deployment_inspect_provider._http")
    @patch("agentos_node.deployment_inspect_provider.SITEFILE")
    def test_new_site_canary_still_not_full_effective_nginx_receipt(self, sitefile, http):
        sitefile.resolve.return_value = Path("/etc/nginx/sites-available/studio.milkcat.org")
        sitefile.read_text.return_value = "server {\n root /home/ubuntu/studio-web/dist;\n}"
        http.return_value = (200, "studio-web-production-root/v1")
        result = _status("deployment.studio.inspect")
        self.assertEqual(result["classification"], "STUDIO_EFFECTIVE_VHOST_UNVERIFIED")
        self.assertFalse(result["successful"])

    @patch("agentos_node.deployment_inspect_provider._run")
    @patch("agentos_node.deployment_inspect_provider._http")
    def test_agentos_active_service_is_not_version_parity(self, http, run):
        from subprocess import CompletedProcess
        run.return_value = CompletedProcess([], 0, "active\n", "")
        http.return_value = (200, "<html>Log in</html>")
        result = _status("deployment.agentos.inspect")
        self.assertEqual(result["classification"], "AGENTOS_CONSOLE_RELEASE_UNVERIFIED")
        self.assertFalse(result["successful"])

    @patch("agentos_node.deployment_inspect_provider._run")
    def test_agentos_missing_service_is_fail_closed(self, run):
        from subprocess import CompletedProcess
        run.return_value = CompletedProcess([], 1, "", "sensitive credential")
        result = _status("deployment.agentos.inspect")
        self.assertEqual(result["classification"], "AGENTOS_CONSOLE_SERVICE_UNAVAILABLE")
        self.assertNotIn("sensitive", str(result))

    @patch("agentos_node.deployment_inspect_provider._status")
    def test_existing_provider_registry_filters_result(self, status):
        status.return_value = {
            "verdict": "FAIL", "classification": "STUDIO_CANARY_MISMATCH",
            "successful": False, "authorized": True, "executor_available": True,
            "routable": True, "credential_exposed": False, "private": "DO_NOT_LEAK",
        }
        registry = ExecutorJobProviderRegistry()
        register_deployment_inspection_providers(registry)
        result = run_registered_executor_job(
            request=canonical_executor_job_request("deployment.studio.inspect"),
            registry=registry,
        )
        self.assertEqual(result["classification"], "STUDIO_CANARY_MISMATCH")
        self.assertFalse(result["successful"])
        self.assertNotIn("private", result)

if __name__ == "__main__":
    unittest.main()
