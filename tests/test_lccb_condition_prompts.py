from research.lccb_condition_prompts import build_condition_messages


def _event(seq, op, key, value, ref):
    meta = {"sequence": seq, "op": op, "key": key, "value": value}
    return {"metadata": meta, "source_ref": ref}


def _task(stage=100):
    return {"stage": stage, "task_key": "state:alpha", "prompt": "What is alpha?"}


def test_b0_contains_no_experience():
    messages = build_condition_messages([_event(1, "set_fact", "alpha", "old", "r1")], [_task()], 100, "B0")
    assert "NO PRIOR EXPERIENCE" in messages[1]["content"]
    assert '"old"' not in messages[1]["content"]


def test_b1_contains_full_visible_history():
    events = [_event(1, "set_fact", "alpha", "old", "r1"), _event(2, "set_fact", "alpha", "new", "r2")]
    text = build_condition_messages(events, [_task()], 100, "B1")[1]["content"]
    assert '"old"' in text and '"new"' in text


def test_b3_projects_latest_semantic_state_only():
    events = [_event(1, "set_fact", "alpha", "old", "r1"), _event(2, "set_fact", "alpha", "new", "r2")]
    text = build_condition_messages(events, [_task()], 100, "B3")[1]["content"]
    assert '"new"' in text
    assert '"old"' not in text


def test_unknown_condition_rejected():
    try:
        build_condition_messages([], [_task()], 100, "BX")
    except ValueError as exc:
        assert "unknown condition" in str(exc)
    else:
        raise AssertionError("expected ValueError")
