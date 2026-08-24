import json

from research.lccb_openai_compatible import build_batch_messages, parse_task_answers, tasks_for_stage
from research.lccb_public_tasks import public_tasks
from research.lccb_synthetic import generate_pack


def _events(pack):
    return [item.to_dict() for item in pack.events]


def _tasks(pack):
    return [item.__dict__ for item in public_tasks(pack.labels)]


def test_batch_prompt_uses_only_events_visible_at_stage():
    pack = generate_pack()
    messages = build_batch_messages(_events(pack), _tasks(pack), 100)
    user = messages[1]["content"]
    assert '"sequence":100' in user
    assert '"sequence":101' not in user
    assert "expected_facts" not in user
    assert "forbidden_facts" not in user


def test_stage_tasks_are_paired_and_public():
    pack = generate_pack()
    tasks = _tasks(pack)
    keys0 = [item["task_key"] for item in tasks_for_stage(tasks, 0)]
    keys100 = [item["task_key"] for item in tasks_for_stage(tasks, 100)]
    keys1000 = [item["task_key"] for item in tasks_for_stage(tasks, 1000)]
    assert keys0 == keys100 == keys1000


def test_parse_answers_accepts_plain_or_fenced_json_and_rejects_key_drift():
    keys = ("a", "b")
    assert parse_task_answers('{"a":"x","b":"y"}', keys) == {"a": "x", "b": "y"}
    fenced = '```json\n{"a":"x","b":"y"}\n```'
    assert parse_task_answers(fenced, keys) == {"a": "x", "b": "y"}
    try:
        parse_task_answers('{"a":"x"}', keys)
    except ValueError as exc:
        assert "task-key mismatch" in str(exc)
    else:
        raise AssertionError("missing answer key must fail closed")
