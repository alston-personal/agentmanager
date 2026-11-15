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


def test_existing_github_workflow_dispatch_is_discoverable_before_build(tmp_path):
    """Existing Runner Window capability must not be treated as absent again."""
    from pathlib import Path
    from agent_core.capability_gate import resolve_before_build
    from runtime_core.capability_resolution import ResolutionMode
    from agent_core.runner_window import resolve_intent
    from agent_core.governance_directory import load_directory

    repo = Path(__file__).resolve().parents[1]
    manifest_dir = repo / "capabilities/github_actions_dispatch"
    manifest = json.loads((manifest_dir / "capability-manifest.json").read_text(encoding="utf-8"))
    assert manifest["lifecycle"] == "implemented"
    assert manifest["capability_id"] == "github.actions.workflow.dispatch"
    assert manifest["invocation"]["intent_registry"] == "agent_core/runner_window.py"

    entry, _ = resolve_intent(
        "github.actions", "workflow.dispatch", source_commit="a" * 40,
        payload={"workflow": "oracle-core-bundle-immutable-runtime-convergence.yml",
                 "ref": "main", "inputs": {"teams_only": "true"}},
    )
    assert entry.action == "agentos.github_actions.workflow_dispatch"

    registry = tmp_path / "directory.json"
    mirrored = sync_discoverable_capability_manifests(
        capability_root=repo / "capabilities", directory_path=registry
    )
    assert any(entity.id == "service://agentos.github-actions.workflow-dispatch" for entity in mirrored)
    assert load_directory(registry)["entities"][
        "service://agentos.github-actions.workflow-dispatch"
    ]["state"] == "implemented"
    result = resolve_before_build(
        ["github.actions.workflow.dispatch"], path=registry,
        allow_build_when_missing=True,
    )
    assert result.mode is ResolutionMode.REUSE
    assert result.selected_candidate_ids == ("service://agentos.github-actions.workflow-dispatch",)
    assert result.build_allowed is False
