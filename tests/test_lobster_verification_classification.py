import ast
from pathlib import Path

def classifier():
    source = Path("scripts/lobster.py").read_text()
    mod = ast.parse(source)
    fn = next(x for x in mod.body if isinstance(x, ast.FunctionDef) and x.name == "classify_inspector_failure")
    namespace = {}
    exec(compile(ast.Module(body=[fn], type_ignores=[]), "<classifier>", "exec"), namespace)
    return namespace["classify_inspector_failure"]

def test_known_failure_codes():
    classify = classifier()
    assert classify("實體檔案缺失") == "PHYSICAL_OUTPUT"
    assert classify("pytest failures") == "TEST_FAILURE"
    assert classify("evidence missing") == "EVIDENCE_MISSING"
    assert classify("驗收失敗") == "ACCEPTANCE_FAILURE"
    assert classify("other unsafe / private text") == "UNCLASSIFIED"

def test_failure_detail_is_never_copied():
    classify = classifier()
    text = "PRIVATE_TOKEN test failure"
    assert classify(text) == "TEST_FAILURE"
    assert "PRIVATE_TOKEN" not in classify(text)
