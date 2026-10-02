from pathlib import Path


def test_content_publish_live_workflows_do_not_impersonate_ubuntu_with_sudo():
    root = Path(__file__).resolve().parents[1]
    for rel in (
        ".github/workflows/content-publish-social-consumer.yml",
        ".github/workflows/oracle-x-auth-inspect.yml",
    ):
        text = (root / rel).read_text(encoding="utf-8")
        assert "sudo -n -u ubuntu" not in text
        assert "ubuntu-owned Action Relay reconcile timer" in text


def test_content_publish_live_workflows_wait_for_capability_marker():
    root = Path(__file__).resolve().parents[1]
    social = (root / ".github/workflows/content-publish-social-consumer.yml").read_text(encoding="utf-8")
    xprobe = (root / ".github/workflows/oracle-x-auth-inspect.yml").read_text(encoding="utf-8")
    assert "agentos.content.social.bootstrap" in social
    assert "agentos.content.social.inspect" in social
    assert "agentos.content.x.auth.inspect" in xprobe
    for text in (social, xprobe):
        assert "/home/ubuntu/agent-data/runtime/action-relay/capabilities.json" in text
        assert "action_relay_generation=PASS" in text
