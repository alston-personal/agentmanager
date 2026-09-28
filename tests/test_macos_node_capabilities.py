from pathlib import Path
s=Path('agentos_node/thin_client.py').read_text(encoding='utf-8')

def test_process_inspect_is_executable_not_manifest_only():
    assert "'process.inspect'" in s
    assert "elif action == 'process.inspect':" in s
    assert "def _inspect_processes" in s

def test_macos_open_url_is_advertised_and_bounded():
    assert "elif platform.system() == 'Darwin':" in s
    assert "caps.append('desktop.open_url')" in s
    assert "parsed.scheme not in {'http','https'}" in s
    assert "subprocess.run(['open', url]" in s
