from pathlib import Path


ROOT = Path(__file__).resolve().parents[1] / ".agent/scripts"


def test_issuer_trigger_is_only_owner_approval_change():
    path = (ROOT / "agentos-paw-trusted-issuer.path").read_text()
    service = (ROOT / "agentos-paw-trusted-issuer.service").read_text()
    assert "PathChanged=/etc/agentos/paw-issuer/approval.json" in path
    assert "Unit=agentos-paw-trusted-issuer.service" in path
    assert "PathChanged=/home/ubuntu/agent-data" not in path
    assert "PathExists=/home/ubuntu/agent-data" not in path
    assert not any(line.strip() == "[Install]" for line in path.splitlines() if not line.lstrip().startswith("#"))
    assert not any(line.strip() == "[Install]" for line in service.splitlines() if not line.lstrip().startswith("#"))
    assert "User=agentos-issuer" in service
    assert "LoadCredential=signing-key:/etc/agentos/paw-issuer/ed25519.key" in service
    assert "LoadCredential=approved-request:/etc/agentos/paw-issuer/approval.json" in service
    assert "ExecStart=/home/ubuntu/agent-data/runtime/core/current/.venv/bin/python3 -m agentos_node.paw_trusted_issuer_cli" in service
    assert "ExecStart=/usr/bin/python3" not in service
    assert "paw_trusted_delivery" not in service
