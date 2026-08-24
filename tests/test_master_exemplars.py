from pathlib import Path

import pytest

from runtime_core.master_exemplars import load_master_exemplars, render_master_bootstrap


PACK = Path("contracts/master-trace-exemplars-v1.json")


def test_master_exemplar_pack_loads():
    exemplars = load_master_exemplars(PACK)
    assert len(exemplars) >= 6
    assert len({item.exemplar_id for item in exemplars}) == len(exemplars)


def test_bootstrap_contains_execution_invariant_and_boundaries():
    text = render_master_bootstrap(load_master_exemplars(PACK))
    assert "answerability is not completion" in text.lower()
    assert "REQUEST_AUTHORITY" in text
    assert "CONTINUE" in text
    assert "INTERRUPTED_BY_USER" in text


def test_invalid_duplicate_ids_fail(tmp_path):
    path = tmp_path / "bad.json"
    path.write_text(
        '{"schema":"agentos.master-trace-exemplars/v1","exemplars":['
        '{"id":"x","observation":"o","decision":"d","action":"a","expected_disposition":"CONTINUE"},'
        '{"id":"x","observation":"o2","decision":"d2","action":"a2","expected_disposition":"CONTINUE"}]}'
    )
    with pytest.raises(ValueError, match="unique"):
        load_master_exemplars(path)
