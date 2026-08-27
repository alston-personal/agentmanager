from agentos_node import mcp_read_tools


class FakeClient:
    def __init__(self):
        self.project_calls = []
        self.task_calls = []

    def get_project_state(self, project_id):
        self.project_calls.append(project_id)
        return {"projectId": project_id, "recommendedAction": "continue"}

    def get_task(self, task_id):
        self.task_calls.append(task_id)
        return {"task": {"taskId": task_id, "status": "succeeded"}}


def test_project_state_is_read_only_passthrough():
    client = FakeClient()
    result = mcp_read_tools.get_project_state(client, "layout-3d")
    assert result["projectId"] == "layout-3d"
    assert client.project_calls == ["layout-3d"]


def test_task_is_read_only_passthrough():
    client = FakeClient()
    result = mcp_read_tools.get_task(client, "task-123")
    assert result["task"]["taskId"] == "task-123"
    assert client.task_calls == ["task-123"]


def test_resume_delegates_to_chatgpt_bootstrap(monkeypatch):
    class Packet:
        def to_dict(self):
            return {"protocol": "agentos.chatgpt-web-bootstrap/v1", "project_id": "layout-3d"}

    seen = {}

    def fake_bootstrap(client, project_id, *, runtime_id):
        seen.update(client=client, project_id=project_id, runtime_id=runtime_id)
        return Packet()

    monkeypatch.setattr(mcp_read_tools, "bootstrap_chatgpt_web", fake_bootstrap)
    client = object()
    result = mcp_read_tools.resume_project(client, "layout-3d", runtime_id="chatgpt-web:test")

    assert result["protocol"] == "agentos.chatgpt-web-bootstrap/v1"
    assert seen == {
        "client": client,
        "project_id": "layout-3d",
        "runtime_id": "chatgpt-web:test",
    }
