from scripts.check_project_release_lane import decide


def test_layoutlib_development_main_denied():
    assert decide("layoutlib", "development_write", "main") == (
        False,
        "development_write_to_promotion_branch_denied",
    )


def test_layoutlib_development_develop_allowed():
    assert decide("layoutlib", "development_write", "develop") == (
        True,
        "development_lane_allowed",
    )


def test_layoutlib_feature_allowed():
    assert decide("layoutlib", "development_write", "feature/door-recovery")[0] is True


def test_layoutlib_promotion_requires_human_approval():
    assert decide("layoutlib", "promotion", "main") == (
        False,
        "explicit_human_approval_required",
    )
    assert decide("layoutlib", "promotion", "main", True) == (
        True,
        "promotion_allowed",
    )


def test_layoutlib_poc_requires_develop():
    assert decide("layoutlib", "poc_deploy", "main") == (
        False,
        "poc_requires_develop_candidate",
    )
    assert decide("layoutlib", "poc_deploy", "develop") == (
        True,
        "poc_candidate_allowed",
    )


def test_layoutlib_production_requires_main():
    assert decide("layoutlib", "production_deploy", "develop") == (
        False,
        "production_requires_promoted_state",
    )
    assert decide("layoutlib", "production_deploy", "main") == (
        True,
        "production_candidate_allowed",
    )
