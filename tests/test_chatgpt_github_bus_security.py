import importlib.util
from pathlib import Path


def _module():
    path = Path(__file__).resolve().parents[1] / "scripts" / "process_chatgpt_github_request.py"
    spec = importlib.util.spec_from_file_location("process_chatgpt_github_request", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_safe_resume_drops_payload_remote_path_and_credentials():
    module = _module()
    raw = {
        "protocol": "agentos.chatgpt-web-bootstrap/v1",
        "project_id": "demo",
        "current_ir_id": "ir_1",
        "current_ir_digest": "abc",
        "execution_context": {
            "active_goal": "continue demo",
            "current_ir": {
                "schema_version": "agentos.ir/v1",
                "ir_id": "ir_1",
                "project_id": "demo",
                "goal": "continue demo",
                "capability": "agentos.project.inspect",
                "payload": {
                    "remote": "https://x-access-token:SECRET@example.invalid/repo.git",
                    "path": "/home/user/private",
                    "token": "SECRET",
                },
            },
            "latest_task": {
                "taskId": "task_1",
                "status": "succeeded",
                "payload": {"token": "SECRET"},
                "result": {"remote": "https://SECRET@example.invalid/repo.git"},
            },
        },
        "request": {"canonical_ir": {"payload": {"token": "SECRET"}}},
    }

    safe = module._safe_resume(raw)
    text = repr(safe)
    assert "SECRET" not in text
    assert "remote" not in text
    assert "payload" not in text
    assert "/home/user/private" not in text
    assert safe["execution_context"]["current_ir"]["goal"] == "continue demo"
    assert safe["execution_context"]["latest_task"]["taskId"] == "task_1"
