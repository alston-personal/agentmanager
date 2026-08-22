from pathlib import Path

from agentos_node.node_identity import device_fingerprint, ensure_node_identity


def test_existing_node_identity_key_is_reused_without_private_key_exposure(tmp_path) -> None:
    private_key = tmp_path / "identity_ed25519"
    public_key = tmp_path / "identity_ed25519.pub"
    private_key.write_text("PRIVATE-TEST-MATERIAL\n", encoding="utf-8")
    public_key.write_text("ssh-ed25519 AAAATEST agentos-node\n", encoding="utf-8")

    material = ensure_node_identity(tmp_path)
    assert material.public_key == "ssh-ed25519 AAAATEST agentos-node"
    assert "PRIVATE-TEST-MATERIAL" not in repr(material)
    assert material.device_fingerprint.startswith("dev_")


def test_device_fingerprint_is_stable_within_host() -> None:
    assert device_fingerprint() == device_fingerprint()
