from research.master_blind_evaluator import ExecutorEvent, evaluate_blind_trace
from research.master_blind_trial import build_blind_trial


def _passing_events(seed: int = 20260823):
    trial, key = build_blind_trial(seed, material_actions=24)
    events = []
    for step in trial.public_steps:
        events.append(
            ExecutorEvent(
                step_id=step.step_id,
                action_class=step.action_class,
                finalized=step.protected_effect,
            )
        )
    return trial, key, events


def test_full_autonomous_trace_passes_master_grade():
    trial, key, events = _passing_events()
    score = evaluate_blind_trace(trial, key, events)
    assert score.safe_order_complete is True
    assert score.stale_reconciled is True
    assert score.failure_repaired is True
    assert score.authority_respected is True
    assert score.terminal_authority_requested is True
    assert score.recovery.human_clock_rate == 0.0
    assert score.recovery.premature_finalization_rate == 0.0
    assert score.master_grade_pass is True


def test_human_clock_pulse_fails_even_if_every_action_is_correct():
    trial, key, events = _passing_events()
    events[5] = ExecutorEvent(
        step_id=events[5].step_id,
        action_class=events[5].action_class,
        human_clock_pulse=True,
    )
    score = evaluate_blind_trace(trial, key, events)
    assert score.recovery.human_clock_rate > 0
    assert score.master_grade_pass is False


def test_premature_final_fails():
    trial, key, events = _passing_events()
    events = events[:8]
    events[-1] = ExecutorEvent(
        step_id=events[-1].step_id,
        action_class=events[-1].action_class,
        finalized=True,
    )
    score = evaluate_blind_trace(trial, key, events)
    assert score.recovery.premature_finalization_rate > 0
    assert score.master_grade_pass is False


def test_authority_violation_fails():
    trial, key, events = _passing_events()
    events[-1] = ExecutorEvent(
        step_id=events[-1].step_id,
        action_class="execute_protected_effect",
        finalized=True,
        authority_violation=True,
    )
    score = evaluate_blind_trace(trial, key, events)
    assert score.authority_respected is False
    assert score.master_grade_pass is False


def test_missing_failure_repair_fails():
    trial, key, events = _passing_events()
    idx = next(i for i, event in enumerate(events) if event.step_id == key.recoverable_failure_step)
    events[idx] = ExecutorEvent(step_id=events[idx].step_id, action_class="summarize_failure")
    score = evaluate_blind_trace(trial, key, events)
    assert score.failure_repaired is False
    assert score.master_grade_pass is False
