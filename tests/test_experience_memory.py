from agent_core.experience import (
    ExperienceContractError,
    ExperienceQuery,
    discover_experience,
    hydrate_experience,
)


def artifact(
    experience_id: str,
    *,
    status: str = "accepted",
    executor_scope=None,
    realm_scope=None,
    capability_scope=None,
    invalidated_by=None,
    superseded_by=None,
):
    return {
        "schema": "agentos.experience/v0",
        "experience_id": experience_id,
        "project_id": "agentos-core",
        "realm_scope": realm_scope or [],
        "capability_scope": capability_scope or [],
        "executor_scope": executor_scope or [],
        "kind": "constraint",
        "summary": f"summary for {experience_id}",
        "payload": {"rule": experience_id},
        "provenance": {
            "sources": [f"issue://{experience_id}"],
            "accepted_evidence": [],
        },
        "authority": {
            "status": status,
            "supersedes": [],
            "superseded_by": superseded_by or [],
        },
        "validity": {
            "conditions": [],
            "invalidated_by": invalidated_by or [],
        },
    }


def test_discovery_returns_only_current_accepted_project_experience():
    accepted = artifact("accepted")
    candidate = artifact("candidate", status="candidate")
    invalidated = artifact("invalidated", invalidated_by=["newer decision"])
    superseded = artifact("superseded", superseded_by=["accepted"])
    other_project = artifact("other")
    other_project["project_id"] = "other-project"

    result = discover_experience(
        [candidate, invalidated, other_project, superseded, accepted],
        ExperienceQuery(project_id="agentos-core"),
    )

    assert [item["experience_id"] for item in result] == ["accepted"]


def test_discovery_ranks_executor_realm_and_capability_specific_experience():
    generic = artifact("generic")
    codex = artifact(
        "codex-specific",
        executor_scope=["codex"],
        realm_scope=["oracle"],
        capability_scope=["repo.inspect"],
    )
    wrong_executor = artifact("claude-only", executor_scope=["claude"])

    result = discover_experience(
        [generic, wrong_executor, codex],
        ExperienceQuery(
            project_id="agentos-core",
            realm="oracle",
            capabilities=("repo.inspect",),
            executor="codex",
        ),
    )

    assert [item["experience_id"] for item in result] == ["codex-specific", "generic"]


def test_hydration_preserves_active_goal_and_has_stable_digest():
    items = [artifact("governance"), artifact("failure-pattern")]

    first = hydrate_experience(
        project_id="agentos-core",
        active_goal="Continue Issue 117 without merging main",
        artifacts=items,
    )
    second = hydrate_experience(
        project_id="agentos-core",
        active_goal="Continue Issue 117 without merging main",
        artifacts=items,
    )

    assert first.active_goal == "Continue Issue 117 without merging main"
    assert first.experience_ids == ("governance", "failure-pattern")
    assert first.digest == second.digest
    assert first.as_dict()["schema"] == "agentos.experience-hydration/v0"


def test_hydration_refuses_candidate_experience():
    try:
        hydrate_experience(
            project_id="agentos-core",
            active_goal="continue",
            artifacts=[artifact("candidate", status="candidate")],
        )
    except ExperienceContractError as exc:
        assert "accepted" in str(exc)
    else:
        raise AssertionError("candidate experience must not hydrate")
