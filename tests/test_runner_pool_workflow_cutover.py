from pathlib import Path

SOCIAL = Path(".github/workflows/oracle-social-runtime-rollout.yml")
MIO = Path(".github/workflows/oracle-publish-mio-approved.yml")


def _assert_runner_window_workflow(path: Path):
    text = path.read_text(encoding="utf-8")
    assert "id-token: write" in text
    assert "scripts/agentos_dispatch.sh" in text
    assert "audience=agentos-scheduler" in text
    assert "webfactory/ssh-agent" not in text
    assert "submit_oracle_bootstrap_request_remote.sh" not in text
    assert "AGENTOS_DEPLOY_SSH_KEY" not in text
    assert "agentos-oracle-hosted-ingress" not in text


def test_social_runtime_uses_runner_window():
    _assert_runner_window_workflow(SOCIAL)
    text = SOCIAL.read_text(encoding="utf-8")
    assert "social.runtime deploy" in text
    assert "social_runtime_runner_window_receipt=PASS" in text


def test_mio_approved_publish_uses_runner_window():
    _assert_runner_window_workflow(MIO)
    text = MIO.read_text(encoding="utf-8")
    assert "social.publish mio.approved" in text
    assert "mio_approved_runner_window_receipt=PASS" in text
