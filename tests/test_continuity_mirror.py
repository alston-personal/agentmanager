import base64
from io import BytesIO
import json
from pathlib import Path
from urllib.error import HTTPError

from agent_core.continuity_mirror import (
    GitHubContinuityMirror,
    MirroringDispatchingGatewayService,
    build_continuity_snapshot,
)
from agent_core.distributed_control_plane import DistributedControlPlane
from agent_core.push_dispatch import ResilientRuntimeDispatcher
from runtime_core.canonical_ir import CanonicalIR


class _Response:
    def __init__(self, status: int, payload: bytes):
        self.status = status
        self._payload = payload

    def read(self):
        return self._payload

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


class _CreateOnlyGitHub:
    def __init__(self):
        self.put_payload = None
        self.put_url = None

    def __call__(self, request, timeout=0):
        if request.method == "GET":
            raise HTTPError(request.full_url, 404, "not found", {}, BytesIO(b""))
        assert request.method == "PUT"
        self.put_url = request.full_url
        self.put_payload = json.loads(request.data.decode("utf-8"))
        return _Response(201, json.dumps({"commit": {"sha": "abc123"}}).encode("utf-8"))


class _ConflictThenCreateGitHub:
    def __init__(self):
        self.put_attempts = 0

    def __call__(self, request, timeout=0):
        if request.method == "GET":
            raise HTTPError(request.full_url, 404, "not found", {}, BytesIO(b""))
        self.put_attempts += 1
        if self.put_attempts == 1:
            raise HTTPError(request.full_url, 409, "conflict", {}, BytesIO(b"{}"))
        return _Response(201, json.dumps({"commit": {"sha": "after-retry"}}).encode("utf-8"))


def _state(ir: CanonicalIR) -> dict:
    return {
        "projectId": ir.project_id,
        "latestTask": {
            "taskId": "task-1",
            "status": "submitted",
            "capability": ir.capability,
            "projectId": ir.project_id,
            "updatedAt": "2026-08-21T00:00:00Z",
        },
        "currentIR": ir.to_dict(),
        "currentSource": "task_input",
        "recommendedAction": "wait",
    }


def test_continuity_snapshot_binds_current_ir_digest():
    ir = CanonicalIR(goal="resume in ChatGPT", project_id="agentmanager", capability="agent.reason")
    snapshot = build_continuity_snapshot(_state(ir))
    assert snapshot["protocol"] == "agentos.continuity-mirror/v1"
    assert snapshot["project_id"] == "agentmanager"
    assert snapshot["current_ir_digest"] == ir.digest()
    assert snapshot["canonical_ir"]["ir_id"] == ir.ir_id


def test_github_continuity_mirror_creates_private_checkpoint_payload():
    ir = CanonicalIR(goal="mirror state", project_id="agentmanager", capability="agent.reason")
    fake = _CreateOnlyGitHub()
    mirror = GitHubContinuityMirror(
        "alston-personal/my-agent-data",
        "secret-token",
        opener=fake,
    )
    result = mirror.publish(_state(ir))
    assert result["status"] == "published"
    assert result["commit"] == "abc123"
    assert result["path"] == "projects/agentmanager/continuity/latest.json"
    assert fake.put_url.endswith("/projects/agentmanager/continuity/latest.json")
    decoded = base64.b64decode(fake.put_payload["content"])
    payload = json.loads(decoded)
    assert payload["current_ir_digest"] == ir.digest()
    assert "secret-token" not in decoded.decode("utf-8")


def test_github_continuity_mirror_retries_one_optimistic_conflict():
    ir = CanonicalIR(goal="retry conflict", project_id="agentmanager", capability="agent.reason")
    fake = _ConflictThenCreateGitHub()
    mirror = GitHubContinuityMirror("alston-personal/my-agent-data", "token", opener=fake)
    result = mirror.publish(_state(ir))
    assert result["status"] == "published"
    assert result["commit"] == "after-retry"
    assert fake.put_attempts == 2


def test_github_continuity_mirror_encodes_unsafe_project_id_as_one_path_segment():
    mirror = GitHubContinuityMirror("alston-personal/my-agent-data", "token", opener=_CreateOnlyGitHub())
    path = mirror.path_for("../team/demo")
    assert path.startswith("projects/~/") is False
    assert path.startswith("projects/~")
    assert path.endswith("/continuity/latest.json")
    project_segment = path.removeprefix("projects/").removesuffix("/continuity/latest.json")
    assert "/" not in project_segment
    assert ".." not in project_segment


def test_mirror_failure_does_not_fail_control_plane_submit(tmp_path: Path):
    store = DistributedControlPlane(tmp_path / "mirror.sqlite3")
    dispatcher = ResilientRuntimeDispatcher(store)

    class BrokenMirror:
        def publish(self, state):
            raise RuntimeError("mirror offline")

    service = MirroringDispatchingGatewayService(store, dispatcher, BrokenMirror())
    ir = CanonicalIR(goal="keep working", project_id="demo", capability="agent.reason")
    response = service.submit({"canonical_ir": ir.to_dict()})
    assert response["task"]["status"] == "submitted"
    assert response["continuityMirror"]["status"] == "degraded"
    assert "mirror offline" in response["continuityMirror"]["error"]
