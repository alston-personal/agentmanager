from scripts.oracle_codex_experience_regression import required_uplift_for_baseline


def test_required_uplift_keeps_full_target_when_headroom_allows_it():
    assert required_uplift_for_baseline(0.0) == 0.34
    assert required_uplift_for_baseline(0.5) == 0.34


def test_required_uplift_is_ceiling_limited_for_strong_baseline():
    required = required_uplift_for_baseline(6 / 7)
    assert abs(required - (1 / 7)) < 1e-12
    assert abs(((1.0 - 6 / 7) - required)) < 1e-12


def test_perfect_baseline_has_no_observable_uplift_headroom():
    assert required_uplift_for_baseline(1.0) == 0.0
