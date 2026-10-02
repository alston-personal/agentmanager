from pathlib import Path

SOCIAL = Path(".github/workflows/oracle-social-runtime-rollout.yml")
MIO = Path(".github/workflows/oracle-publish-mio-approved.yml")


def _assert_https_scheduler_workflow(path: Path):
    text = path.read_text(encoding="utf-8")
    assert "id-token: write" in text
    assert "submit_agentos_scheduler_request_https.sh" in text
    assert "audience=agentos-scheduler" in text
    assert "webfactory/ssh-agent" not in text
    assert "submit_oracle_bootstrap_request_remote.sh" not in text
    assert "AGENTOS_DEPLOY_SSH_KEY" not in text
    assert "agentos-oracle-hosted-ingress" not in text


def test_social_runtime_uses_oidc_https_scheduler():
    _assert_https_scheduler_workflow(SOCIAL)
    text = SOCIAL.read_text(encoding="utf-8")
    assert "agentos.social_runtime.deploy" in text
    assert "social_runtime_scheduler_receipt=PASS" in text


def test_mio_approved_publish_uses_oidc_https_scheduler():
    _assert_https_scheduler_workflow(MIO)
    text = MIO.read_text(encoding="utf-8")
    assert "agentos.social_threads_mio_approved.publish" in text
    assert "mio_approved_receipt=PASS" in text
