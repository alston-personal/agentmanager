from __future__ import annotations

import pytest

from agent_core.experience_observation import (
    ExperienceObservationError,
    compile_experience_observations,
)


def _item(experience_id: str, predicate: str, value, value_type: str = "boolean"):
    return {
        "experience_id": experience_id,
        "expected_behavior_dimensions": [predicate],
        "ir": {
            "schema": "agentos.experience-ir/v1",
            "nodes": [
                {
                    "id": "observation",
                    "op": "set",
                    "predicate": predicate,
                    "value": {"type": value_type, "value": value},
                }
            ],
        },
    }


def test_compile_observations_uses_explicit_ir_set_nodes_only():
    hydration = {
        "project_id": "agentos-core",
        "digest": "sha256:test",
        "items": [
            _item("branch.v1", "canonical_development_branch", "core/integration", "string"),
            _item("authority.v1", "generic_continue_authorizes_main_merge", False),
        ],
    }
    result = compile_experience_observations(
        hydration,
        allowed_dimensions=(
            "canonical_development_branch",
            "generic_continue_authorizes_main_merge",
        ),
    )
    assert result["values"] == {
        "canonical_development_branch": "core/integration",
        "generic_continue_authorizes_main_merge": False,
    }
    assert result["sources"]["canonical_development_branch"] == ["branch.v1"]
    assert result["missing_dimensions"] == []
    assert result["derived_from_experience_ir"] is True


def test_compile_observations_reports_missing_without_guessing():
    hydration = {"project_id": "agentos-core", "items": []}
    result = compile_experience_observations(
        hydration,
        allowed_dimensions=("workspace_is_continuation_authority",),
    )
    assert result["values"] == {}
    assert result["missing_dimensions"] == ["workspace_is_continuation_authority"]


def test_compile_observations_rejects_conflicting_experience():
    hydration = {
        "project_id": "agentos-core",
        "items": [
            _item("a.v1", "workspace_is_continuation_authority", False),
            _item("b.v1", "workspace_is_continuation_authority", True),
        ],
    }
    with pytest.raises(ExperienceObservationError, match="conflicting"):
        compile_experience_observations(hydration)
