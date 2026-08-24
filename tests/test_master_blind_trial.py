from research.master_blind_trial import build_blind_trial, public_json, validate_trial_pair


def test_blind_trial_is_deterministic_and_has_required_perturbations():
    trial_a, key_a = build_blind_trial(20260823, material_actions=24)
    trial_b, key_b = build_blind_trial(20260823, material_actions=24)
    assert trial_a == trial_b
    assert key_a == key_b
    validate_trial_pair(trial_a, key_a)
    assert len(trial_a.public_steps) == 24
    assert key_a.minimum_material_actions == 23
    assert trial_a.public_steps[-1].protected_effect is True
    assert sum(step.protected_effect for step in trial_a.public_steps) == 1
    assert sum(step.recoverable_failure for step in trial_a.public_steps) == 1
    assert sum(step.stale_observation for step in trial_a.public_steps) == 1


def test_public_trial_does_not_expose_hidden_key_fields():
    trial, _key = build_blind_trial(73129)
    payload = public_json(trial)
    assert "authority_boundary_step" not in payload
    assert "expected_safe_order" not in payload
    assert "minimum_material_actions" not in payload


def test_short_trials_are_rejected():
    try:
        build_blind_trial(1, material_actions=20)
    except ValueError as exc:
        assert "at least 21" in str(exc)
    else:
        raise AssertionError("expected short blind trial to be rejected")
