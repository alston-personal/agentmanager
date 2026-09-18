from runtime_core.capability_resolution import (
    CapabilityCandidate,
    ResolutionMode,
    resolve_capabilities,
)


def candidate(candidate_id, capabilities, *, priority=0, available=True):
    return CapabilityCandidate.from_values(
        candidate_id,
        capabilities,
        priority=priority,
        available=available,
    )


def test_reuses_single_existing_capability_before_build():
    result = resolve_capabilities(
        ["studio.static-route.release"],
        [candidate("studio-release", ["studio.static-route.release"], priority=10)],
        allow_build_when_missing=True,
    )
    assert result.mode is ResolutionMode.REUSE
    assert result.selected_candidate_ids == ("studio-release",)
    assert not result.build_allowed


def test_composes_existing_capabilities_before_build():
    result = resolve_capabilities(
        ["asset.build", "studio.static-route.release"],
        [
            candidate("release", ["studio.static-route.release"]),
            candidate("builder", ["asset.build"]),
        ],
        allow_build_when_missing=True,
    )
    assert result.mode is ResolutionMode.COMPOSE
    assert set(result.selected_candidate_ids) == {"builder", "release"}


def test_reusable_solution_blocks_forced_build_without_reason():
    result = resolve_capabilities(
        ["tarot.render"],
        [candidate("renderer", ["tarot.render"])],
        force_build=True,
    )
    assert result.mode is ResolutionMode.DENY
    assert "override" in result.reason


def test_explicit_reason_can_override_reuse_gate():
    result = resolve_capabilities(
        ["tarot.render"],
        [candidate("renderer", ["tarot.render"])],
        force_build=True,
        override_reason="existing renderer cannot satisfy the new isolation boundary",
    )
    assert result.mode is ResolutionMode.BUILD
    assert result.override_reason
    assert result.selected_candidate_ids == ("renderer",)


def test_missing_capability_requires_build_authority():
    denied = resolve_capabilities(["credits.ledger"], [])
    allowed = resolve_capabilities(
        ["credits.ledger"], [], allow_build_when_missing=True
    )
    assert denied.mode is ResolutionMode.DENY
    assert denied.missing_capabilities == ("credits.ledger",)
    assert allowed.mode is ResolutionMode.BUILD


def test_resolution_is_deterministic_for_equal_candidates():
    candidates = [
        candidate("z-provider", ["x"]),
        candidate("a-provider", ["x"]),
    ]
    first = resolve_capabilities(["x"], candidates)
    second = resolve_capabilities(["x"], list(reversed(candidates)))
    assert first == second
    assert first.selected_candidate_ids == ("a-provider",)


def test_unavailable_candidate_is_not_reused():
    result = resolve_capabilities(
        ["x"],
        [candidate("offline", ["x"], available=False)],
        allow_build_when_missing=True,
    )
    assert result.mode is ResolutionMode.BUILD
    assert result.missing_capabilities == ("x",)
