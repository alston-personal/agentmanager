from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "oracle_codex_experience_ablation.py"


def test_ablation_target_and_repeat_count_are_fixed_in_trusted_source():
    text = SCRIPT.read_text(encoding="utf-8")
    assert 'WITHHELD_EXPERIENCE_ID = "core.branch-authority.v2"' in text
    assert 'TARGET_DIMENSION = "canonical_development_branch"' in text
    assert "REPEAT_COUNT = 3" in text
    assert 'parser.add_argument("--output", required=True)' in text
    assert 'parser.add_argument("--timeout", type=int, default=180)' in text
    assert "--experience-id" not in text
    assert "--target-dimension" not in text
    assert "--repeat-count" not in text


def test_ablation_is_read_only_counterfactual_not_store_mutation():
    text = SCRIPT.read_text(encoding="utf-8")
    assert "discover_from_one(query)" in text
    assert "hydrate_experience(" in text
    assert "filtered = [item for item in discovered" in text
    assert "seed_experience_set" not in text
    assert "converge_experience_set" not in text
    assert "write_text" in text  # evidence file only
    assert '"credential_exposed": False' in text
