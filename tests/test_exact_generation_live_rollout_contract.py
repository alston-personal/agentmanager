import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REPAIR = ROOT / "scripts" / "repair_antigravity_relay_user.sh"
BOOTSTRAP = ROOT / "agentos_node" / "bootstrap_control.py"
WORKFLOW = ROOT / ".github" / "workflows" / "oracle-exact-generation-executor-job-rollout.yml"
LEGACY_BOOTSTRAP_WORKFLOW = ROOT / ".github" / "workflows" / "oracle-bootstrap-transport-control-plane.yml"


def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


class ExactGenerationLiveRolloutContractTests(unittest.TestCase):
    def test_transport_repair_fails_closed_on_generation_drift(self):
        text = _text(REPAIR)
        self.assertIn('EXPECTED_SOURCE_COMMIT="${AGENTOS_SOURCE_COMMIT:-}"', text)
        self.assertIn('^[0-9a-f]{40}$', text)
        self.assertIn('[ "$SOURCE_COMMIT" != "$EXPECTED_SOURCE_COMMIT" ]', text)
        self.assertIn('runtime source generation mismatch', text)
        self.assertIn('AGENTOS_ACTION_SOURCE_COMMIT="$SOURCE_COMMIT"', text)

    def test_bootstrap_exact_repair_owns_integration_lane_selection(self):
        text = _text(BOOTSTRAP)
        self.assertIn('env_extra["AGENTOS_REF"] = "core/integration"', text)
        self.assertIn('env["AGENTOS_SOURCE_COMMIT"] = source_commit', text)
        self.assertNotIn('source_ref', text.split('unknown = set(params) - {"source_commit"}', 1)[0])

    def test_rollout_is_integration_only_and_never_writes_main(self):
        text = _text(WORKFLOW)
        self.assertIn('branches:\n      - core/integration', text)
        self.assertIn('"params": {"source_commit": sha}', text)
        self.assertIn('agentos_source_ref=core/integration', text)
        self.assertNotIn('git push', text)
        self.assertNotIn('HEAD:main', text)
        self.assertNotIn('origin/main', text)

    def test_rollout_scopes_cross_owner_git_trust_without_global_mutation(self):
        text = _text(WORKFLOW)
        self.assertIn('git -c safe.directory="$RUNTIME" -C "$RUNTIME" rev-parse HEAD', text)
        self.assertNotIn('git config --global --add safe.directory', text)

    def test_live_submission_enters_one_controller_before_action_relay(self):
        text = _text(WORKFLOW)
        self.assertIn('http://127.0.0.1:8780/v1/controller/dispatch', text)
        self.assertIn('"schema": "agentos.controller-dispatch/v0.1"', text)
        self.assertIn('"node_id": "oracle-core-node"', text)
        self.assertIn('"action": "agentos.executor.job"', text)
        self.assertIn('assert submission.get("schema") == "agentos.executor-job-submission/v1"', text)
        self.assertIn('assert submission.get("task_id") == job_id', text)
        self.assertIn('one_controller_dispatch=PASS', text)
        submit_section = text.split('Submit through ONE and collect bounded executor receipt', 1)[1]
        self.assertNotIn('dispatcher.submit(', submit_section)

    def test_rollout_records_bounded_executor_job_receipt_without_requiring_workload_success(self):
        text = _text(WORKFLOW)
        self.assertIn('canonical_experience_regression_request', text)
        self.assertIn('ActionRelayExecutorJobDispatcher', text)
        self.assertIn('dispatcher.inspect(job_id)', text)
        self.assertIn('credential_exposed', text)
        self.assertIn('executor_job_transport_receipt=PASS', text)
        self.assertIn('actions/upload-artifact@v4', text)
        self.assertNotIn("assert receipt['successful'] is True", text)

    def test_legacy_bootstrap_is_manual_read_only_and_exact_generation_only(self):
        text = _text(LEGACY_BOOTSTRAP_WORKFLOW)
        compact = text.replace(' ', '')
        trigger = text.split('permissions:', 1)[0]
        self.assertIn('workflow_dispatch:', trigger)
        self.assertNotIn('\n  push:', trigger)
        self.assertIn('permissions:\n  contents: read', text)
        self.assertIn("test \"$GITHUB_REF\" = 'refs/heads/core/integration'", text)
        self.assertIn("'params':{'source_commit':sha}", compact)
        self.assertIn("assertr.get('source_commit')==expected", compact)
        self.assertNotIn('contents: write', text)
        self.assertNotIn('git push', text)
        self.assertNotIn('HEAD:main', text)
        self.assertNotIn('git reset --hard origin/main', text)
        self.assertIn('bootstrap_evidence_scope=RUNNER_WORKSPACE_ONLY', text)


if __name__ == "__main__":
    unittest.main()
