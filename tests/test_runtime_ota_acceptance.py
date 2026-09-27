from agent_core.runtime_ota_acceptance import accept_candidate

def test_acceptance_module_requires_runtime_commit_and_probe():
    import inspect
    s=inspect.getsource(accept_candidate)
    assert "runtime.get('source_commit')==source_commit" in s
    assert "'action':'agent.surface.inspect'" in s
    assert "'receipt_ok':ok" in s

# trigger transactional OTA contract guard
