import json

from agent_core.capability_manifest_adapter import sync_discoverable_capability_manifests
from agent_core.governance_directory import load_directory


def test_opt_in_capability_manifest_is_mirrored_without_hardcoded_provider(tmp_path):
    root = tmp_path / "capabilities"
    cap = root / "demo"
    cap.mkdir(parents=True)
    (cap / "capability-manifest.json").write_text(
        json.dumps(
            {
                "schema": "agentos.capability-manifest/v1",
                "capability_id": "web.static-index.render",
                "display_name": "Web Static Index Renderer",
                "semantic_owner": "web-static-index",
                "version": "0.1.0",
                "lifecycle": "implemented",
                "contract": {"inputs": ["web.page-summary"], "outputs": ["text/html"]},
                "invocation": {"kind": "python-cli", "entrypoint": "scripts/web_static_index.py"},
                "discovery": {
                    "governance_directory": True,
                    "provider_id": "service://web.static-index.renderer",
                    "reuse_before_build": True,
                },
            }
        ),
        encoding="utf-8",
    )

    directory = tmp_path / "directory.json"
    mirrored = sync_discoverable_capability_manifests(
        capability_root=root,
        directory_path=directory,
    )

    assert len(mirrored) == 1
    registry = load_directory(directory)
    provider = registry["entities"]["service://web.static-index.renderer"]
    assert provider["provides"] == ["capability://web.static-index.render"]
    assert provider["implementation"]["invocation"]["entrypoint"] == "scripts/web_static_index.py"
    assert provider["authority"]["reuse_before_build"] is True


def test_non_opt_in_manifest_is_not_mirrored(tmp_path):
    root = tmp_path / "capabilities"
    cap = root / "demo"
    cap.mkdir(parents=True)
    (cap / "capability-manifest.json").write_text(
        json.dumps(
            {
                "schema": "agentos.capability-manifest/v1",
                "capability_id": "demo.capability",
                "display_name": "Demo",
                "semantic_owner": "demo",
                "version": "0.1.0",
                "lifecycle": "implemented"
            }
        ),
        encoding="utf-8",
    )

    mirrored = sync_discoverable_capability_manifests(
        capability_root=root,
        directory_path=tmp_path / "directory.json",
    )
    assert mirrored == []


def test_implemented_manifest_without_machine_entrypoint_is_rejected(tmp_path):
    import pytest

    root = tmp_path / "capabilities"
    cap = root / "unbacked"
    cap.mkdir(parents=True)
    (cap / "capability-manifest.json").write_text(
        json.dumps({
            "schema": "agentos.capability-manifest/v1",
            "capability_id": "demo.unbacked",
            "lifecycle": "implemented",
            "invocation": {"kind": "llm-prompt"},
            "discovery": {
                "governance_directory": True,
                "provider_id": "service://demo.unbacked",
            },
        }),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="machine invocation"):
        sync_discoverable_capability_manifests(
            capability_root=root,
            directory_path=tmp_path / "directory.json",
        )


def test_declared_capability_may_await_machine_entrypoint(tmp_path):
    root = tmp_path / "capabilities"
    cap = root / "planned"
    cap.mkdir(parents=True)
    (cap / "capability-manifest.json").write_text(
        json.dumps({
            "schema": "agentos.capability-manifest/v1",
            "capability_id": "demo.planned",
            "lifecycle": "declared",
            "invocation": {},
            "discovery": {
                "governance_directory": True,
                "provider_id": "service://demo.planned",
            },
        }),
        encoding="utf-8",
    )
    mirrored = sync_discoverable_capability_manifests(
        capability_root=root,
        directory_path=tmp_path / "directory.json",
    )
    assert len(mirrored) == 1
    assert mirrored[0].state == "declared"


def test_model_chat_cannot_be_the_machine_entrypoint_even_if_named(tmp_path):
    import pytest

    root = tmp_path / "capabilities"
    cap = root / "chat-only"
    cap.mkdir(parents=True)
    (cap / "capability-manifest.json").write_text(
        json.dumps({
            "schema": "agentos.capability-manifest/v1",
            "capability_id": "demo.chat-only",
            "lifecycle": "stable",
            "invocation": {"kind": "llm-prompt", "entrypoint": "remember to do it"},
            "discovery": {
                "governance_directory": True,
                "provider_id": "service://demo.chat-only",
            },
        }),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="machine invocation"):
        sync_discoverable_capability_manifests(
            capability_root=root,
            directory_path=tmp_path / "directory.json",
        )
