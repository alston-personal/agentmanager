import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
EXT = ROOT / "browser" / "chatgpt-agentos-node"


def test_extension_manifest_is_chatgpt_scoped_and_loopback_only():
    manifest = json.loads((EXT / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["manifest_version"] == 3
    hosts = set(manifest["host_permissions"])
    assert "https://chatgpt.com/*" in hosts
    assert "https://chat.openai.com/*" in hosts
    assert "http://127.0.0.1:8766/*" in hosts
    assert all("studio.milkcat.org" not in host for host in hosts)


def test_content_script_is_fail_closed_and_does_not_embed_one_credentials():
    content = (EXT / "content.js").read_text(encoding="utf-8")
    assert "http://127.0.0.1:8766/v1/resume" in content
    assert "current_ir_digest" in content
    assert "已阻止直接猜測" in content
    assert "AGENTOS_CONTROL_PLANE_TOKEN" not in content
    assert "studio.milkcat.org" not in content


def test_extension_keeps_only_routing_and_companion_transport_metadata():
    popup = (EXT / "popup.js").read_text(encoding="utf-8")
    assert "activeProjectId" in popup
    assert "companionToken" in popup
    assert "canonical_ir" not in popup
    assert "execution_context" not in popup
