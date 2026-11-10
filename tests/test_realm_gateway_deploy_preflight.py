"""Guard against the 2026-11-10 failed Oracle Gateway deploy preflight.

The inherited integration version defined the immutable source paths, but
main accidentally lost the definitions while retaining set -u references.
These assertions are deliberately static: PR CI must never mutate Oracle.
"""
import re
import unittest
from pathlib import Path

SCRIPT = Path("scripts/deploy_realm_gateway_user.sh")
WORKFLOW = Path(".github/workflows/oracle-deploy-realm-gateway.yml")
SCHEDULER = Path("agentos_node/bootstrap_scheduler.py")


class GatewayDeployPreflightTest(unittest.TestCase):
    def test_source_variables_are_defined_before_first_reference(self):
        source = SCRIPT.read_text(encoding="utf-8")
        lines = source.splitlines()
        self.assertIn("set -euo pipefail", source)
        for variable in (
            "DASH", "PORT_MANAGER_REL", "PORT_MANAGER_EXACT",
            "RETIRE_PM2_REL", "RETIRE_PM2_EXACT",
            "ROUTE_REL", "ROUTE", "DATA_ROOT", "PUBLIC", "PUBLIC_BOOTSTRAP",
        ):
            with self.subTest(variable=variable):
                declaration = next(
                    (i for i, line in enumerate(lines)
                     if re.match(r"^" + re.escape(variable) + r"=", line)), None)
                self.assertIsNotNone(declaration, variable + " is undefined")
                reference = next(
                    (i for i, line in enumerate(lines)
                     if re.search(r"\$" + re.escape(variable) + r"\b|\$\{" +
                                  re.escape(variable) + r"(?=[}:])", line)
                     and not line.startswith(variable + "=")), None)
                self.assertIsNotNone(reference, variable + " is unused")
                self.assertLess(declaration, reference,
                                variable + " referenced before initialized")

    def test_gateway_workflow_matches_current_scheduler_role(self):
        workflow = WORKFLOW.read_text(encoding="utf-8")
        scheduler = SCHEDULER.read_text(encoding="utf-8")
        self.assertRegex(
            scheduler,
            r'bc\.ACTION_DEPLOY_REALM_GATEWAY:\s*ActionPolicy\("maintenance"')
        self.assertIn("assert s.get('worker_role') == 'maintenance'", workflow)
        self.assertIn("assert s.get('worker_id') == 'oracle-maintenance'", workflow)
        self.assertIn("if: ${{ github.event_name != 'pull_request' }}", workflow)


if __name__ == "__main__":
    unittest.main()
