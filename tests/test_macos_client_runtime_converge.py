from pathlib import Path
s=Path('agentos_node/client_runtime_converge.py').read_text(encoding='utf-8')
t=Path('agentos_node/thin_client.py').read_text(encoding='utf-8')

def test_macos_runtime_converge_is_transactional():
    for marker in ['versions','last-known-good.json','awaiting-controller-acceptance','rollback_deadline','ota-guard.py','StartInterval','candidate_import=PASS']:
        assert marker in s, marker
    assert "os.replace(tmp,path)" in s
    assert "phase not in {'stage','accept','rollback'}" in s
    assert 'def _deferred_kick' in s
    assert "_deferred_kick(LABEL)" in s

def test_runtime_converge_capability_matches_execute():
    assert "elif action == 'node.runtime.converge':" in t
    assert "execute_client_runtime_converge(task)" in t
    assert "caps.extend(['desktop.open_url', 'node.runtime.converge'])" in t
