import json
from pathlib import Path

from agent_core.capability_gate import resolve_before_build
from runtime_core.capability_resolution import ResolutionMode


def write_directory(path: Path, entities: dict):
    path.write_text(
        json.dumps({"schema_version": "0.1", "updated_at": None, "entities": entities}),
        encoding="utf-8",
    )


def test_existing_governed_provider_is_reused(tmp_path: Path):
    registry = tmp_path / "directory.json"
    write_directory(
        registry,
        {
            "service://studio.release": {
                "id": "service://studio.release",
                "kind": "service",
                "state": "verified",
                "owns": [],
                "provides": ["capability://studio.static-route.release"],
                "authority": {"exclusive": False},
                "implementation": {"path": ".github/workflows/reusable-studio-static-route-release.yml"},
            }
        },
    )

    result = resolve_before_build(
        ["studio.static-route.release"],
        path=registry,
        allow_build_when_missing=True,
    )
    assert result.mode is ResolutionMode.REUSE
    assert result.selected_candidate_ids == ("service://studio.release",)


def test_stale_provider_does_not_block_missing_capability_build(tmp_path: Path):
    registry = tmp_path / "directory.json"
    write_directory(
        registry,
        {
            "service://old": {
                "id": "service://old",
                "kind": "service",
                "state": "stale",
                "owns": [],
                "provides": ["capability://x"],
                "authority": {},
                "implementation": {},
            }
        },
    )

    result = resolve_before_build(["x"], path=registry, allow_build_when_missing=True)
    assert result.mode is ResolutionMode.BUILD
    assert result.missing_capabilities == ("capability://x",)


def test_exclusive_owner_wins_deterministically(tmp_path: Path):
    registry = tmp_path / "directory.json"
    write_directory(
        registry,
        {
            "service://ordinary": {
                "id": "service://ordinary",
                "kind": "service",
                "state": "verified",
                "owns": [],
                "provides": ["capability://x"],
                "authority": {"exclusive": False},
                "implementation": {},
            },
            "manager://canonical": {
                "id": "manager://canonical",
                "kind": "manager",
                "state": "implemented",
                "owns": ["capability://x"],
                "provides": ["capability://x"],
                "authority": {"exclusive": True},
                "implementation": {},
            },
        },
    )

    result = resolve_before_build(["x"], path=registry)
    assert result.mode is ResolutionMode.REUSE
    assert result.selected_candidate_ids == ("manager://canonical",)
