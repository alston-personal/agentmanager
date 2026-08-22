import json

from research.lccb_synthetic import (
    CAPABILITY_KEYS,
    PROCEDURE_KEYS,
    STATE_KEYS,
    STAGES,
    generate_pack,
    private_labels_jsonl,
    public_experience_jsonl,
)


def labels_by_stage(pack, stage):
    return {item.task_key: item for item in pack.labels if item.stage == stage}


def test_synthetic_pack_is_deterministic_and_content_addressed():
    first = generate_pack()
    second = generate_pack()
    assert len(first.events) == len(second.events) == 1000
    assert first.experience_manifest_hash == second.experience_manifest_hash
    assert first.evaluator_manifest_hash == second.evaluator_manifest_hash
    assert [item.event_id for item in first.events] == [item.event_id for item in second.events]


def test_same_task_keys_are_paired_across_all_longitudinal_stages():
    pack = generate_pack()
    key_sets = [set(labels_by_stage(pack, stage)) for stage in STAGES]
    assert key_sets[0] == key_sets[1] == key_sets[2]
    expected_count = len(STATE_KEYS) + len(PROCEDURE_KEYS) + len(CAPABILITY_KEYS) + 1
    assert len(key_sets[0]) == expected_count


def test_age_zero_requires_unknown_instead_of_using_benchmark_future():
    pack = generate_pack()
    age_zero = labels_by_stage(pack, 0)
    assert age_zero
    assert all(item.expected_facts == ("unknown",) for item in age_zero.values())
    assert all(item.evidence_source_refs == () for item in age_zero.values())


def test_later_stage_supersession_labels_forbid_obsolete_values():
    pack = generate_pack()
    age_1000 = labels_by_stage(pack, 1000)
    superseded = [item for item in age_1000.values() if item.forbidden_facts]
    assert superseded
    assert any(item.category == "supersession" for item in superseded)
    assert any(item.category == "governance" for item in superseded)
    for item in superseded:
        assert not (set(item.expected_facts) & set(item.forbidden_facts))


def test_public_experience_artifact_does_not_contain_hidden_labels():
    pack = generate_pack()
    public_payload = public_experience_jsonl(pack)
    private_payload = private_labels_jsonl(pack)
    assert '"expected_facts"' not in public_payload
    assert '"forbidden_facts"' not in public_payload
    assert '"expected_facts"' in private_payload
    assert '"forbidden_facts"' in private_payload
    assert public_payload != private_payload


def test_jsonl_artifacts_are_machine_readable_and_separately_hashable():
    pack = generate_pack()
    public_rows = [json.loads(line) for line in public_experience_jsonl(pack).splitlines()]
    private_rows = [json.loads(line) for line in private_labels_jsonl(pack).splitlines()]
    assert len(public_rows) == 1000
    assert len(private_rows) == sum(len(labels_by_stage(pack, stage)) for stage in STAGES)
    assert public_rows[0]["source_ref"] == "lccb:meridian:event:0001"
    assert {row["stage"] for row in private_rows} == set(STAGES)


def test_short_pack_is_rejected_because_it_cannot_cover_age_100():
    try:
        generate_pack(event_count=99)
    except ValueError as exc:
        assert "at least 100" in str(exc)
    else:
        raise AssertionError("short controlled benchmark must fail")
