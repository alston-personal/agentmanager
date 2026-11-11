"""Keep #2198 deployment receipts discoverable without user-supplied Actions URLs.

Source contract tests: no production SSH or GitHub mutations during CI.
"""
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github/workflows/oracle-agentos-login-control-plane-release.yml"


def test_original_deploy_guard_remains_source_pinned_and_rolls_back():
    source = WORKFLOW.read_text(encoding="utf-8")
    assert "AGENTOS_REPO=\"$REPO\" \"$DEPLOY\" \"$SOURCE_SHA\"" in source
    assert 'test "$ACCEPTED" = "$EXPECTED"' in source
    assert "agentos_control_plane_login_release=PASS" in source
    assert "cancel-in-progress: false" in source


def test_release_receipt_does_not_need_manual_run_id_or_new_issue():
    source = WORKFLOW.read_text(encoding="utf-8")
    assert "report-release-receipt:" in source
    assert "needs: [deploy]" in source
    assert "if: ${{ always() }}" in source
    assert "DEPLOY_RESULT: ${{ needs.deploy.result }}" in source
    assert "context.runId" in source
    assert "context.sha" in source
    assert "const issue_number = 2198;" in source
    assert "issues.createComment" in source
    assert "issues.updateComment" in source
    assert "agentos-control-plane-release:" in source


def test_release_reporter_is_least_privilege_and_never_reports_auth_completed():
    source = WORKFLOW.read_text(encoding="utf-8")
    report = source.split("\n  report-release-receipt:", 1)[1]
    assert "issues: write" in report
    assert "ssh-private-key:" not in report
    assert "DEPLOY_USER" not in report
    assert "authenticated admin/tenant sessions remain separate acceptance gates" in report.lower()
    assert "not established" in report.lower()
