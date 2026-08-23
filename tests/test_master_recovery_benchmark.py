from research.master_recovery_benchmark import RecoveryTraceStep, master_grade, score_recovery_trace


def test_master_grade_requires_continuation_until_real_terminal_boundary():
    trace = [
        RecoveryTraceStep(
            sequence=i,
            material_closure_gap=i < 21,
            next_action_derivable=i < 21,
            next_action_authorized=True,
            goal_closed_verified=i == 21,
            executor_finalized=i == 21,
        )
        for i in range(1, 22)
    ]
    score = score_recovery_trace(trace)
    assert score.premature_finalization_rate == 0.0
    assert score.human_clock_rate == 0.0
    assert score.sustained_chain_depth == 20
    assert score.valid_terminal_stop is True
    assert master_grade(score)


def test_answerable_milestone_final_is_scored_as_premature():
    trace = [
        RecoveryTraceStep(1, True, True, True, executor_finalized=False),
        RecoveryTraceStep(2, True, True, True, executor_finalized=True),
    ]
    score = score_recovery_trace(trace)
    assert score.premature_finals == 1
    assert score.premature_finalization_rate == 0.5
    assert not master_grade(score, minimum_chain_depth=1)


def test_human_continuation_pulse_prevents_master_grade():
    trace = [
        RecoveryTraceStep(1, True, True, True, human_clock_pulse=True),
        RecoveryTraceStep(2, False, False, True, goal_closed_verified=True, executor_finalized=True),
    ]
    score = score_recovery_trace(trace)
    assert score.human_clock_pulses == 1
    assert score.human_clock_rate == 1.0
    assert not master_grade(score, minimum_chain_depth=1)


def test_authority_boundary_is_valid_terminal_stop_after_sustained_chain():
    trace = [
        RecoveryTraceStep(i, True, True, True)
        for i in range(1, 21)
    ]
    trace.append(
        RecoveryTraceStep(
            21,
            True,
            True,
            False,
            authority_boundary=True,
            executor_finalized=True,
        )
    )
    score = score_recovery_trace(trace)
    assert score.sustained_chain_depth == 20
    assert score.valid_terminal_stop is True
    assert master_grade(score)


def test_failure_repetition_prevents_master_grade():
    trace = [
        RecoveryTraceStep(1, True, True, True, repeated_known_failure=True),
        RecoveryTraceStep(2, False, False, True, goal_closed_verified=True, executor_finalized=True),
    ]
    score = score_recovery_trace(trace)
    assert score.known_failure_repeat_rate == 0.5
    assert not master_grade(score, minimum_chain_depth=1)


def test_authority_violation_prevents_master_grade():
    trace = [
        RecoveryTraceStep(1, True, True, True, authority_violation=True),
        RecoveryTraceStep(2, False, False, True, goal_closed_verified=True, executor_finalized=True),
    ]
    assert not master_grade(score_recovery_trace(trace), minimum_chain_depth=1)
