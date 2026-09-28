from pathlib import Path
s=Path('scripts/bootstrap_macos_transactional_runtime.py').read_text(encoding='utf-8')

def test_bootstrap_uses_candidate_runtime_converge():
    assert "versions" in s
    assert "venv.EnvBuilder" in s
    assert "agentos_node.client_runtime_converge" in s
    assert "'phase':'stage'" in s
    assert "awaiting-controller-acceptance" in s
    assert "agentos_macos_transactional_bootstrap=PASS" in s
