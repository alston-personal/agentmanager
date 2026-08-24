from agentos_node.local_cognition_discovery import discover_local_cognition


def test_scanner_emits_hashes_not_content_and_skips_sensitive_paths(tmp_path) -> None:
    root = tmp_path / "cognition"
    root.mkdir()
    (root / "memory.json").write_text('{"fact":"hello"}', encoding="utf-8")
    secret_dir = root / "secrets"
    secret_dir.mkdir()
    (secret_dir / "token.txt").write_text("SUPERSECRET", encoding="utf-8")
    (root / "binary.bin").write_bytes(b"ignored")

    descriptors = discover_local_cognition((root,), project_id="project-a")
    assert len(descriptors) == 1
    item = descriptors[0]
    assert item.local_ref == "memory.json"
    assert item.kind == "memory"
    assert item.content_hash.startswith("sha256:")
    assert item.project_id == "project-a"
    assert "hello" not in repr(item)
    assert "SUPERSECRET" not in repr(descriptors)


def test_scanner_ignores_symlink_escape(tmp_path) -> None:
    root = tmp_path / "cognition"
    root.mkdir()
    outside = tmp_path / "outside.txt"
    outside.write_text("outside", encoding="utf-8")
    (root / "link.txt").symlink_to(outside)

    assert discover_local_cognition((root,)) == ()
