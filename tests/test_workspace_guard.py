from agentos_node.workspace_guard import WorkspaceGuard


def contract():
    return {
        "schema": "agentos.node-workspace-contract/v1",
        "paths": [
            {
                "path": "/home/ubuntu/agent-data",
                "role": "canonical_data",
                "allowed_effects": ["read", "write", "create", "delete"],
                "protected_patterns": ["secrets/**", "**/cookies.txt", "**/*.key"],
                "allowed_write_patterns": [
                    "projects/agentmanager/STATUS.md",
                    "projects/agentmanager/continuity/**",
                    "runtime/receipts/**",
                ],
            },
            {
                "path": "/home/ubuntu/agentmanager",
                "role": "logic_workspace",
                "allowed_effects": ["read"],
                "forbidden_effects": ["write", "create", "delete", "commit"],
            },
        ],
    }


def test_allows_explicit_agentmanager_status_write():
    decision = WorkspaceGuard(contract()).evaluate(
        "/home/ubuntu/agent-data/projects/agentmanager/STATUS.md", "write"
    )
    assert decision.allowed


def test_denies_secret_even_with_os_write_permission():
    decision = WorkspaceGuard(contract()).evaluate(
        "/home/ubuntu/agent-data/secrets/youtube-ai-manager/cookies.txt", "write"
    )
    assert not decision.allowed
    assert "protected" in decision.reason


def test_denies_unrelated_project_write():
    decision = WorkspaceGuard(contract()).evaluate(
        "/home/ubuntu/agent-data/projects/youtube-ai-manager/video_library.json", "write"
    )
    assert not decision.allowed
    assert "allowlisted" in decision.reason


def test_denies_logic_workspace_write():
    decision = WorkspaceGuard(contract()).evaluate(
        "/home/ubuntu/agentmanager/README.md", "write"
    )
    assert not decision.allowed


def test_denies_path_outside_contract():
    decision = WorkspaceGuard(contract()).evaluate("/home/ubuntu/.ssh/config", "read")
    assert not decision.allowed
